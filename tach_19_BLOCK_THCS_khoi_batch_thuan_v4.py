from __future__ import annotations

import ast
import hashlib
import json
import os
import shutil
import subprocess
import sys
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

ROSTER = (
    ROOT
    / "data"
    / "school_merger_source_rosters"
    / "THCS_2025_2026.json"
)

RESOLUTION = (
    ROOT
    / "data"
    / "school_merger_registry"
    / "qd3805_thcs_resolution.json"
)

HISTORY = (
    ROOT
    / "data"
    / "school_merger_approved_plans.json"
)

SOURCE_SCRIPT = (
    ROOT
    / "tach_19_BLOCK_THCS_khoi_batch_thuan.py"
)


EXPECTED = {
    "db":
        "882e4925fd3e39d7e097ce127612c093"
        "852075e608d3f937294135282afec75a",

    "service":
        "9104fb99c78755e9eec86d090659b3a9"
        "22834ff097d7292aa4d4b29e360a27f9",

    "lock":
        "ad310048a4c5b239404e0902cc04fda1"
        "d73474d11a739a2ca009d2727e4390c3",

    "roster":
        "926528e0ae600a6b950b459c6f8ec5c"
        "6810e69d49158d1ff3c9a3d76c0bca657",

    "resolution":
        "d447e7475d1631051a6e7e04ac8d1c81"
        "fcb4b171d7f0d0980b963b1f07bedbc1",

    "history":
        "4e2c5f044c48c57dda40fecc11f4e9f"
        "466f236aacc082f224536b1685cadb1fc",
}


SPECIAL_IDS = {
    "QD3805-OP-0025",
    "QD3805-OP-0108",
    "QD3805-OP-0126",
    "QD3805-OP-0132",
    "QD3805-OP-0133",
    "QD3805-OP-0153",
    "QD3805-OP-0160",
    "QD3805-OP-0172",
    "QD3805-OP-0191",
    "QD3805-OP-0203",
    "QD3805-OP-0210",
    "QD3805-OP-0399",
    "QD3805-OP-0424",
    "QD3805-OP-0434",
    "QD3805-OP-0451",
    "QD3805-OP-0486",
    "QD3805-OP-0489",
    "QD3805-OP-0490",
    "QD3805-OP-0644",
}


READY_IDS = {
    "QD3805-OP-0011",
    "QD3805-OP-0014",
    "QD3805-OP-0026",
    "QD3805-OP-0027",
    "QD3805-OP-0028",
    "QD3805-OP-0034",
    "QD3805-OP-0035",
    "QD3805-OP-0042",
    "QD3805-OP-0043",
    "QD3805-OP-0050",
    "QD3805-OP-0051",
    "QD3805-OP-0061",
    "QD3805-OP-0068",
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


def load_rules():

    if not SOURCE_SCRIPT.exists():

        raise RuntimeError(
            "DUNG: khong tim thay:\n"
            + str(SOURCE_SCRIPT)
        )


    source = SOURCE_SCRIPT.read_text(
        encoding="utf-8-sig"
    )


    tree = ast.parse(
        source,
        filename=str(SOURCE_SCRIPT),
    )


    found = []


    for node in tree.body:

        if not isinstance(
            node,
            ast.Assign,
        ):
            continue


        if any(
            isinstance(target, ast.Name)
            and target.id == "RULES"
            for target in node.targets
        ):
            found.append(node)


    if len(found) != 1:

        raise RuntimeError(
            "DUNG: khong tim thay "
            "duy nhat bien RULES."
        )


    rules = ast.literal_eval(
        found[0].value
    )


    if not isinstance(
        rules,
        list,
    ):
        raise RuntimeError(
            "DUNG: RULES khong phai list."
        )


    rules = [
        dict(x)
        for x in rules
        if isinstance(
            x,
            dict,
        )
    ]


    ids = [
        str(
            x.get(
                "operation_id"
            )
            or ""
        )
        for x in rules
    ]


    if len(rules) != 19:

        raise RuntimeError(
            "DUNG: RULES khong bang 19."
        )


    if set(ids) != SPECIAL_IDS:

        print(
            "RULE IDS =",
            sorted(ids),
        )

        raise RuntimeError(
            "DUNG: 19 operation_id khong khop."
        )


    if len(ids) != len(set(ids)):

        raise RuntimeError(
            "DUNG: RULES co operation trung."
        )


    return rules


def fresh_state():

    code = r'''
import json
from collections import Counter

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


special_ops = [
    str(
        x.get(
            "operation_id"
        )
        or ""
    )
    for x in (
        ctx.get(
            "special_ops"
        )
        or []
    )
]


special_counter = Counter(
    special_ops
)


out = {
    "summary":
        svc.registry_level_summary(
            "THCS"
        ),

    "counts":
        counts,

    "candidate_count":
        preview.get(
            "candidate_count"
        ),

    "effective_block_count":
        preview.get(
            "effective_block_count"
        ),

    "ready_for_execution":
        preview.get(
            "ready_for_execution"
        ),

    "registry_unresolved_count":
        preview.get(
            "registry_unresolved_count"
        ),

    "registry_deferred_unresolved_count":
        preview.get(
            "registry_deferred_unresolved_count"
        ),

    "ready_ops": sorted(
        str(
            x.get(
                "qd3805_operation_id"
            )
            or ""
        )
        for x in rows
        if str(
            x.get(
                "batch_state"
            )
            or ""
        ).upper()
        == "READY"
    ),

    "block_ops": sorted(
        str(
            x.get(
                "qd3805_operation_id"
            )
            or ""
        )
        for x in rows
        if str(
            x.get(
                "batch_state"
            )
            or ""
        ).upper()
        == "BLOCK"
    ),

    "done_precompleted": sorted(
        str(
            x.get(
                "qd3805_operation_id"
            )
            or ""
        )
        for x in rows
        if str(
            x.get(
                "batch_state"
            )
            or ""
        ).upper()
        == "DONE"
        and str(
            x.get(
                "qd3805_operation_id"
            )
            or ""
        )
        in {
            "QD3805-OP-0342",
            "QD3805-OP-0343",
        }
    ),

    "special_ops":
        special_ops,

    "special_counter":
        dict(
            special_counter
        ),

    "special_duplicates":
        {
            k: v
            for k, v
            in special_counter.items()
            if v > 1
        },

    "special_orphans":
        ctx.get(
            "special_orphans"
        )
        or [],
}


print(
    "JSON_RESULT="
    + json.dumps(
        out,
        ensure_ascii=False,
        default=str,
    )
)
'''


    env = dict(
        os.environ
    )

    env[
        "PYTHONDONTWRITEBYTECODE"
    ] = "1"


    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            code,
        ],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


    if proc.returncode != 0:

        print(proc.stdout)
        print(proc.stderr)

        raise RuntimeError(
            "Fresh-process FAIL."
        )


    for line in proc.stdout.splitlines():

        if line.startswith(
            "JSON_RESULT="
        ):

            return json.loads(
                line[
                    len(
                        "JSON_RESULT="
                    ):
                ]
            )


    raise RuntimeError(
        "Khong tim thay JSON_RESULT."
    )


print("=" * 144)
print(
    "THCS - TACH 19 BLOCK V3 - SUA VALIDATOR NGHI HUONG"
)
print("=" * 144)

print(
    "CHI SUA RESOLUTION."
)

print(
    "KHONG SUA SERVICE."
)

print(
    "KHONG GHI DATABASE."
)

print(
    "KHONG CHAY SAP NHAP THCS."
)


# ============================================================
# 1. HASH GATE
# ============================================================

print()
print("=" * 144)
print("1. HASH GATE")
print("=" * 144)


PATHS = {
    "db":
        DB,

    "service":
        SERVICE,

    "lock":
        LOCK,

    "roster":
        ROSTER,

    "resolution":
        RESOLUTION,

    "history":
        HISTORY,
}


before = {}


for key, path in PATHS.items():

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


for suffix in (
    "-wal",
    "-journal",
):

    p = Path(
        str(DB)
        + suffix
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
            "DUNG: server/Uvicorn chua dung."
        )


# ============================================================
# 2. PRECHECK
# ============================================================

print()
print("=" * 144)
print("2. PRECHECK")
print("=" * 144)


state_before = fresh_state()


print(
    "COUNTS       =",
    state_before.get(
        "counts"
    ),
)

print(
    "CANDIDATE    =",
    state_before.get(
        "candidate_count"
    ),
)

print(
    "BLOCK EFFECT =",
    state_before.get(
        "effective_block_count"
    ),
)


if (
    state_before.get(
        "counts"
    )
    != {
        "KEEP": 36,
        "DONE": 84,
        "READY": 13,
        "BLOCK": 19,
    }
):

    raise RuntimeError(
        "DUNG: precheck khong con "
        "36/84/13/19."
    )


if set(
    state_before.get(
        "block_ops"
    )
    or []
) != SPECIAL_IDS:

    raise RuntimeError(
        "DUNG: tap 19 BLOCK da thay doi."
    )


if set(
    state_before.get(
        "ready_ops"
    )
    or []
) != READY_IDS:

    raise RuntimeError(
        "DUNG: tap 13 READY da thay doi."
    )


# ============================================================
# 3. LOAD RULES
# ============================================================

rules = load_rules()


print()
print("=" * 144)
print("3. LOAD 19 RULES")
print("=" * 144)


print(
    "RULE COUNT =",
    len(rules),
)


for rule in rules:

    print(
        rule[
            "operation_id"
        ],
        "|",
        rule.get(
            "relation_type"
        ),
    )


# ============================================================
# 4. RESOLUTION GATE
# ============================================================

payload = json.loads(
    RESOLUTION.read_text(
        encoding="utf-8"
    )
)


if (
    payload.get(
        "schema"
    )
    != "QD3805_THCS_RESOLUTION_2026"
):

    raise RuntimeError(
        "DUNG: schema resolution sai."
    )


if (
    payload.get(
        "level_code"
    )
    != "THCS"
):

    raise RuntimeError(
        "DUNG: level_code sai."
    )


if len(
    payload.get(
        "precompleted"
    )
    or []
) != 2:

    raise RuntimeError(
        "DUNG: mat 2 Nghi Loc precompleted."
    )


if (
    payload.get(
        "special_same_level"
    )
    or []
):

    raise RuntimeError(
        "DUNG: special_same_level "
        "khong rong truoc khi cai."
    )


deferred = (
    payload.get(
        "deferred_orphans"
    )
    or []
)


if not any(
    isinstance(x, dict)
    and int(
        x.get("stt")
        or 0
    ) == 110
    and str(
        x.get(
            "school_code"
        )
        or ""
    ) == "40413505"
    and bool(
        x.get(
            "confirmed_keep"
        )
    )
    for x in deferred
):

    raise RuntimeError(
        "DUNG: resolution goc "
        "khong con quy tac Nghi Huong."
    )


# ============================================================
# 5. BACKUP
# ============================================================

stamp = datetime.now().strftime(
    "%Y%m%d_%H%M%S"
)


BACKUP_DIR = (
    ROOT
    / "backups"
    / (
        "backup_truoc_tach_19_BLOCK_THCS_V3_"
        + stamp
    )
)


BACKUP_DIR.mkdir(
    parents=True,
    exist_ok=False,
)


RESOLUTION_BACKUP = (
    BACKUP_DIR
    / "qd3805_thcs_resolution.json"
)


shutil.copy2(
    RESOLUTION,
    RESOLUTION_BACKUP,
)


print()
print("=" * 144)
print("4. BACKUP")
print("=" * 144)


print(
    "BACKUP DIR =",
    BACKUP_DIR,
)


# ============================================================
# 6. UPDATE RESOLUTION
# ============================================================

payload[
    "special_same_level"
] = rules


tmp = RESOLUTION.with_suffix(
    ".json.thcs19v3.tmp"
)


try:

    tmp.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


    check_payload = json.loads(
        tmp.read_text(
            encoding="utf-8"
        )
    )


    check_rules = (
        check_payload.get(
            "special_same_level"
        )
        or []
    )


    check_ids = [
        str(
            x.get(
                "operation_id"
            )
            or ""
        )
        for x in check_rules
        if isinstance(
            x,
            dict,
        )
    ]


    if len(check_ids) != 19:

        raise RuntimeError(
            "Resolution tam khong du 19."
        )


    if set(check_ids) != SPECIAL_IDS:

        raise RuntimeError(
            "Resolution tam sai tap operation."
        )


    if len(
        check_ids
    ) != len(
        set(check_ids)
    ):

        raise RuntimeError(
            "Resolution tam bi trung."
        )


    os.replace(
        tmp,
        RESOLUTION,
    )


    # ========================================================
    # 7. VALIDATE
    # ========================================================

    print()
    print("=" * 144)
    print("5. VALIDATE SAU CAI")
    print("=" * 144)


    state_after = fresh_state()


    print(
        "COUNTS AFTER      =",
        state_after.get(
            "counts"
        ),
    )

    print(
        "CANDIDATE         =",
        state_after.get(
            "candidate_count"
        ),
    )

    print(
        "EFFECTIVE BLOCK   =",
        state_after.get(
            "effective_block_count"
        ),
    )

    print(
        "READY TO EXECUTE  =",
        state_after.get(
            "ready_for_execution"
        ),
    )

    print(
        "UNRESOLVED RAW    =",
        state_after.get(
            "registry_unresolved_count"
        ),
    )

    print(
        "UNRESOLVED DEFER  =",
        state_after.get(
            "registry_deferred_unresolved_count"
        ),
    )

    print(
        "SPECIAL DUPLICATE =",
        state_after.get(
            "special_duplicates"
        ),
    )


    if (
        state_after.get(
            "counts"
        )
        != {
            "KEEP": 36,
            "DONE": 84,
            "READY": 13,
            "BLOCK": 0,
        }
    ):

        raise RuntimeError(
            "DUNG: counts khong dat "
            "36/84/13/0."
        )


    if int(
        state_after.get(
            "candidate_count"
        )
        or 0
    ) != 13:

        raise RuntimeError(
            "DUNG: candidate_count != 13."
        )


    if int(
        state_after.get(
            "effective_block_count"
        )
        or 0
    ) != 0:

        raise RuntimeError(
            "DUNG: van con blocker."
        )


    if (
        state_after.get(
            "ready_for_execution"
        )
        is not True
    ):

        raise RuntimeError(
            "DUNG: THCS chua ready_for_execution."
        )


    if (
        state_after.get(
            "block_ops"
        )
        or []
    ):

        raise RuntimeError(
            "DUNG: van con BLOCK op."
        )


    if set(
        state_after.get(
            "ready_ops"
        )
        or []
    ) != READY_IDS:

        raise RuntimeError(
            "DUNG: 13 READY bi thay doi."
        )


    if (
        state_after.get(
            "done_precompleted"
        )
        != [
            "QD3805-OP-0342",
            "QD3805-OP-0343",
        ]
    ):

        raise RuntimeError(
            "DUNG: mat 2 Nghi Loc DONE."
        )


    summary = (
        state_after.get(
            "summary"
        )
        or {}
    )


    if int(
        summary.get(
            "action_count"
        )
        or 0
    ) != 97:

        raise RuntimeError(
            "DUNG: action_count != 97."
        )


    if int(
        summary.get(
            "keep_count"
        )
        or 0
    ) != 36:

        raise RuntimeError(
            "DUNG: keep_count != 36."
        )


    if int(
        summary.get(
            "special_count"
        )
        or 0
    ) != 108:

        raise RuntimeError(
            "DUNG: special_count != 108."
        )


    special_counter = Counter(
        state_after.get(
            "special_ops"
        )
        or []
    )


    for op in SPECIAL_IDS:

        if special_counter[
            op
        ] != 1:

            raise RuntimeError(
                "DUNG: "
                + op
                + " xuat hien "
                + str(
                    special_counter[
                        op
                    ]
                )
                + " lan."
            )


    if (
        state_after.get(
            "special_duplicates"
        )
        or {}
    ):

        raise RuntimeError(
            "DUNG: con duplicate special."
        )


    # ========================================================
    # QUAN TRỌNG:
    # Object special_orphans thực tế dùng SOURCE_CODES,
    # không dùng SCHOOL_CODE.
    # ========================================================

    special_orphans = (
        state_after.get(
            "special_orphans"
        )
        or []
    )


    nghi_huong_matches = []


    for item in special_orphans:

        if not isinstance(
            item,
            dict,
        ):
            continue


        source_codes = [
            str(x)
            for x in (
                item.get(
                    "source_codes"
                )
                or []
            )
        ]


        if (
            int(
                item.get("stt")
                or 0
            ) == 110
            and "40413505"
                in source_codes
        ):

            nghi_huong_matches.append(
                item
            )


    if len(
        nghi_huong_matches
    ) != 1:

        print(
            "NGHI HUONG MATCHES =",
            json.dumps(
                nghi_huong_matches,
                ensure_ascii=False,
                indent=2,
                default=str,
            ),
        )

        raise RuntimeError(
            "DUNG: khong tim thay duy nhat "
            "Nghi Huong bang source_codes."
        )


    nghi_huong = (
        nghi_huong_matches[0]
    )


    print()
    print(
        "NGHI HUONG =",
        json.dumps(
            nghi_huong,
            ensure_ascii=False,
            default=str,
        ),
    )


    if str(
        nghi_huong.get(
            "school"
        )
        or ""
    ) != "THCS Nghi Hương":

        raise RuntimeError(
            "DUNG: sai ten THCS Nghi Huong."
        )


    if not str(
        nghi_huong.get(
            "status"
        )
        or ""
    ).startswith(
        "GIỮ NGUYÊN"
    ):

        raise RuntimeError(
            "DUNG: Nghi Huong "
            "khong o trang thai GIU NGUYEN."
        )


    if str(
        nghi_huong.get(
            "batch"
        )
        or ""
    ) != "LIÊN CẤP/ĐẶC THÙ":

        raise RuntimeError(
            "DUNG: Nghi Huong "
            "khong duoc tach khoi batch thuan."
        )


    if int(
        state_after.get(
            "registry_deferred_unresolved_count"
        )
        or 0
    ) != 1:

        raise RuntimeError(
            "DUNG: deferred unresolved != 1."
        )


    print(
        "NGHI HUONG CHECK = PASS"
    )


    # ========================================================
    # 8. FILE SAFETY
    # ========================================================

    print()
    print("=" * 144)
    print("6. FILE SAFETY")
    print("=" * 144)


    unchanged = {
        "db":
            sha256(DB),

        "service":
            sha256(SERVICE),

        "lock":
            sha256(LOCK),

        "roster":
            sha256(ROSTER),

        "history":
            sha256(HISTORY),
    }


    for key in (
        "db",
        "service",
        "lock",
        "roster",
        "history",
    ):

        print(
            key,
            ":",
            before[key],
            "->",
            unchanged[key],
        )


        if (
            unchanged[key]
            != before[key]
        ):

            raise RuntimeError(
                "DUNG: "
                + key
                + " bi thay doi."
            )


    print(
        "RESOLUTION OLD SHA =",
        before[
            "resolution"
        ],
    )


    print(
        "RESOLUTION NEW SHA =",
        sha256(
            RESOLUTION
        ),
    )


    print(
        "BACKUP DIR         =",
        BACKUP_DIR,
    )


except Exception:

    print()
    print("=" * 144)
    print("LOI - TU KHOI PHUC RESOLUTION")
    print("=" * 144)


    shutil.copy2(
        RESOLUTION_BACKUP,
        RESOLUTION,
    )


    if tmp.exists():
        tmp.unlink()


    print(
        "RESOLUTION RESTORED =",
        sha256(
            RESOLUTION
        ),
    )


    print(
        "SERVICE KHONG DOI   =",
        sha256(
            SERVICE
        ),
    )


    print(
        "DATABASE KHONG DOI  =",
        sha256(
            DB
        ),
    )


    raise


finally:

    if tmp.exists():
        tmp.unlink()


print()
print("=" * 144)
print("TACH 19 BLOCK THCS V3: THANH CONG")
print("=" * 144)

print(
    "KEEP              = 36"
)

print(
    "DONE              = 84"
)

print(
    "READY             = 13"
)

print(
    "BLOCK             = 0"
)

print(
    "XU LY RIENG       = 19"
)

print(
    "SPECIAL COUNT     = 108"
)

print(
    "DUPLICATE SPECIAL = 0"
)

print(
    "NGHI HUONG        = GIU NGUYEN"
)

print(
    "CANDIDATE         = 13"
)

print(
    "READY_FOR_DRY_RUN = YES"
)

print(
    "DATABASE          = KHONG THAY DOI"
)

print(
    "SERVICE           = KHONG THAY DOI"
)

print(
    "SAP NHAP THCS     = CHUA CHAY"
)

print()
print("13 READY OPS:")


for op in sorted(
    READY_IDS
):

    print(
        " -",
        op,
    )


print("=" * 144)

