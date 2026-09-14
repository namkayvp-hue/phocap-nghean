from __future__ import annotations

import hashlib
import json
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

RESOLUTION = (
    ROOT
    / "data"
    / "school_merger_registry"
    / "qd3805_mn_resolution.json"
)

ROSTER = (
    ROOT
    / "data"
    / "school_merger_source_rosters"
    / "MN_2025_2026.json"
)

REGISTRY_DIR = (
    ROOT
    / "data"
    / "school_merger_registry"
)

EXPECTED_DB = (
    "44b1aa841cdd76301c57d9fc601121ae"
    "96f9312084ef05959eaae54acf17c8c9"
)

EXPECTED_SERVICE = (
    "963b8d6a280d8abef8e96486abd87d77"
    "cea289b08d2edb497647f250ed1b2af8"
)

EXPECTED_RESOLUTION = (
    "bf991e2ebb10a5952f07ca81caa24ead"
    "e98bca5f9e44beded54ae17c68fc373a"
)

EXPECTED_ROSTER = (
    "ef865f74aa51c2700ceb7746d5433b63"
    "fc6a52a4e3169014ebe0e446ac441120"
)

OP_ID = "QD3805-ORPHAN-R1216"
SCHOOL_CODE = "40418311"
STT = 1211


def sha256(path: Path) -> str:
    h = hashlib.sha256()

    with path.open("rb") as f:
        for block in iter(
            lambda: f.read(1024 * 1024),
            b"",
        ):
            h.update(block)

    return h.hexdigest()


def walk_json(
    value,
    path="$",
):
    if isinstance(value, dict):

        if (
            str(
                value.get("operation_id")
                or ""
            )
            == OP_ID
            or str(
                value.get("school_code")
                or ""
            ).replace(
                ".0",
                "",
            )
            == SCHOOL_CODE
            or int(
                value.get("stt")
                or 0
            )
            == STT
        ):
            yield path, value

        for key, child in value.items():
            yield from walk_json(
                child,
                path
                + "."
                + str(key),
            )

    elif isinstance(value, list):

        for i, child in enumerate(
            value
        ):
            yield from walk_json(
                child,
                path
                + f"[{i}]",
            )


before = {
    "db":
        sha256(DB),

    "service":
        sha256(SERVICE),

    "resolution":
        sha256(RESOLUTION),

    "roster":
        sha256(ROSTER),
}


print("=" * 126)
print("CHAN DOAN VI TRI THAT CUA MAM NON LUONG MINH")
print("CHI DOC - KHONG SUA DB / SOURCE / JSON")
print("=" * 126)

for key, value in before.items():
    print(
        f"{key:10s} = {value}"
    )


if before["db"] != EXPECTED_DB:
    raise RuntimeError(
        "DUNG: DB khong dung nen."
    )

if before["service"] != EXPECTED_SERVICE:
    raise RuntimeError(
        "DUNG: service khong dung nen."
    )

if before["resolution"] != EXPECTED_RESOLUTION:
    raise RuntimeError(
        "DUNG: resolution khong dung nen."
    )

if before["roster"] != EXPECTED_ROSTER:
    raise RuntimeError(
        "DUNG: roster khong dung nen."
    )


# ============================================================
# 1. TIM TRONG TAT CA JSON REGISTRY
# ============================================================

print()
print("=" * 126)
print("1. TIM LUONG MINH TRONG CAC JSON REGISTRY")
print("=" * 126)

found = []

for path in sorted(
    REGISTRY_DIR.glob("*.json")
):

    try:
        payload = json.loads(
            path.read_text(
                encoding="utf-8-sig"
            )
        )
    except Exception:
        continue

    matches = list(
        walk_json(payload)
    )

    if not matches:
        continue

    print()
    print(
        "FILE =",
        path,
    )

    print(
        "SHA  =",
        sha256(path),
    )

    for json_path, item in matches:

        print(
            "JSON PATH =",
            json_path,
        )

        print(
            json.dumps(
                item,
                ensure_ascii=False,
                indent=2,
            )
        )

        found.append(
            (
                path,
                json_path,
                item,
            )
        )


print()
print(
    "SO VI TRI TIM THAY =",
    len(found),
)


# ============================================================
# 2. MODULE GLOBAL PATHS
# ============================================================

from app.services import (
    school_merger_level_batch_service
    as svc
)


print()
print("=" * 126)
print("2. CAC PATH REGISTRY/LOCK MA SERVICE DANG DUNG")
print("=" * 126)

for name in sorted(
    svc.__dict__
):

    value = svc.__dict__[name]

    if not isinstance(
        value,
        Path,
    ):
        continue

    upper = name.upper()

    if (
        "LOCK" in upper
        or "REGISTRY" in upper
        or "RESOLUTION" in upper
    ):
        print(
            name,
            "=",
            value,
        )

        if value.exists():
            print(
                "   SHA =",
                sha256(value),
            )


# ============================================================
# 3. CONTEXT MN THAT
# ============================================================

ctx = svc._registry_level_context(
    "MN"
)

print()
print("=" * 126)
print("3. PHAN LOAI NOI BO MN HIEN TAI")
print("=" * 126)

print(
    "pure_actions =",
    len(
        ctx.get(
            "pure_actions"
        )
        or []
    ),
)

print(
    "keep_ops     =",
    len(
        ctx.get(
            "keep_ops"
        )
        or []
    ),
)

print(
    "special_ops  =",
    len(
        ctx.get(
            "special_ops"
        )
        or []
    ),
)

print(
    "unresolved   =",
    len(
        ctx.get(
            "unresolved"
        )
        or []
    ),
)

print()
print(
    "LUONG MINH TRONG KEEP:"
)

for item in (
    ctx.get("keep_ops")
    or []
):
    if (
        str(
            item.get(
                "operation_id"
            )
            or ""
        )
        == OP_ID
        or int(
            item.get("stt")
            or 0
        )
        == STT
    ):
        print(
            json.dumps(
                item,
                ensure_ascii=False,
                indent=2,
            )
        )


print()
print(
    "LUONG MINH TRONG UNRESOLVED:"
)

for item in (
    ctx.get("unresolved")
    or []
):
    if (
        str(
            item.get(
                "operation_id"
            )
            or ""
        )
        == OP_ID
        or int(
            item.get("stt")
            or 0
        )
        == STT
    ):
        print(
            json.dumps(
                item,
                ensure_ascii=False,
                indent=2,
            )
        )


# ============================================================
# 4. PREVIEW HIEN TAI
# ============================================================

preview = (
    svc.build_level_batch_preview(
        school_year_id=2,
        level_code="MN",
    )
)

print()
print("=" * 126)
print("4. KPI HIEN TAI")
print("=" * 126)

print(
    "counts                =",
    preview.get("counts"),
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
    "batch_fingerprint     =",
    preview.get(
        "batch_fingerprint"
    ),
)


# ============================================================
# 5. SAFETY
# ============================================================

after = {
    "db":
        sha256(DB),

    "service":
        sha256(SERVICE),

    "resolution":
        sha256(RESOLUTION),

    "roster":
        sha256(ROSTER),
}


print()
print("=" * 126)
print("5. KIEM TRA AN TOAN")
print("=" * 126)

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
        "DUNG: file da thay doi."
    )


print()
print("=" * 126)
print("CHAN DOAN HOAN TAT")
print("=" * 126)

print(
    "Database/Source/JSON : KHONG THAY DOI"
)

print(
    "Buoc tiep theo       : "
    "chuyen Lượng Minh tu UNRESOLVED/DEFERRED "
    "sang GIU NGUYEN dung registry."
)

print("=" * 126)
