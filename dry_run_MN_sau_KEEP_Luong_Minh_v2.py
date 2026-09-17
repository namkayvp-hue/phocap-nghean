from __future__ import annotations

import hashlib
import sys
from pathlib import Path


try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


ROOT = Path(r"C:\PhoCap")

SOURCE = (
    ROOT
    / "dry_run_tong_cuoi_5_MN_READY.py"
)

DB = (
    ROOT
    / "data"
    / "phocap.db"
)

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


EXPECTED_DB_SHA = (
    "44b1aa841cdd76301c57d9fc601121ae"
    "96f9312084ef05959eaae54acf17c8c9"
)

EXPECTED_SERVICE_SHA = (
    "963b8d6a280d8abef8e96486abd87d77"
    "cea289b08d2edb497647f250ed1b2af8"
)

EXPECTED_LOCK_SHA = (
    "ad310048a4c5b239404e0902cc04fda1"
    "d73474d11a739a2ca009d2727e4390c3"
)

EXPECTED_RESOLUTION_SHA = (
    "22ca7931ec40408ced25a3bde14a9672c"
    "04e12a760a077a44bb9d65b709b1163"
)

EXPECTED_ROSTER_SHA = (
    "ef865f74aa51c2700ceb7746d5433b63"
    "fc6a52a4e3169014ebe0e446ac441120"
)

EXPECTED_NEW_FP = (
    "3ff70145c42c255075bb1430ea4bc4fde"
    "8da38521f7cb344b51349a75875cd60"
)


OLD_RESOLUTION_PART_1 = (
    "bf991e2ebb10a5952f07ca81caa24ead"
)

OLD_RESOLUTION_PART_2 = (
    "e98bca5f9e44beded54ae17c68fc373a"
)

NEW_RESOLUTION_PART_1 = (
    "22ca7931ec40408ced25a3bde14a9672c"
)

NEW_RESOLUTION_PART_2 = (
    "04e12a760a077a44bb9d65b709b1163"
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


print("=" * 126)
print(
    "DRY-RUN TONG CUOI MN V2 "
    "SAU KHI LUONG MINH = GIU NGUYEN"
)
print(
    "CHI DOC - KHONG SUA DB / SOURCE / JSON"
)
print("=" * 126)


# ============================================================
# 1. KIEM TRA NEN THAT
# ============================================================

actual = {
    "db":
        sha256(DB),

    "service":
        sha256(SERVICE),

    "lock":
        sha256(LOCK),

    "resolution":
        sha256(RESOLUTION),

    "roster":
        sha256(ROSTER),
}

expected = {
    "db":
        EXPECTED_DB_SHA,

    "service":
        EXPECTED_SERVICE_SHA,

    "lock":
        EXPECTED_LOCK_SHA,

    "resolution":
        EXPECTED_RESOLUTION_SHA,

    "roster":
        EXPECTED_ROSTER_SHA,
}


print()
print("=" * 126)
print("1. HASH GATE")
print("=" * 126)

for key in actual:
    print(
        f"{key:12s} = {actual[key]}"
    )

    if actual[key] != expected[key]:
        raise RuntimeError(
            "DUNG: "
            + key
            + " khong dung nen da khoa."
        )


if not SOURCE.exists():
    raise RuntimeError(
        "DUNG: khong tim thay dry-run goc: "
        + str(SOURCE)
    )


# ============================================================
# 2. DOC DRY-RUN GOC
# ============================================================

text = SOURCE.read_text(
    encoding="utf-8-sig"
)


required_tokens = [
    "DRY-RUN TONG CUOI 5 PHUONG AN MAM NON READY",
    "build_level_batch_preview",
    "build_official_plan_impact_preview",
    "merger_engine._apply_merge",
    'mem = sqlite3.connect(',
    '":memory:"',
    "mem.rollback()",
]

for token in required_tokens:

    if token not in text:
        raise RuntimeError(
            "DUNG: dry-run goc thieu marker: "
            + token
        )


# Không cho phép vô tình dùng script thực thi thật.
if "execute_level_batch(" in text:
    raise RuntimeError(
        "DUNG: dry-run goc co goi "
        "execute_level_batch."
    )


# ============================================================
# 3. SUA CAC KHOA CHI TRONG RAM
# ============================================================

if (
    text.count(
        OLD_RESOLUTION_PART_1
    )
    != 1
):
    raise RuntimeError(
        "DUNG: khong tim thay dung 1 "
        "Resolution SHA phan 1 cu."
    )


if (
    text.count(
        OLD_RESOLUTION_PART_2
    )
    != 1
):
    raise RuntimeError(
        "DUNG: khong tim thay dung 1 "
        "Resolution SHA phan 2 cu."
    )


text = text.replace(
    OLD_RESOLUTION_PART_1,
    NEW_RESOLUTION_PART_1,
    1,
)

text = text.replace(
    OLD_RESOLUTION_PART_2,
    NEW_RESOLUTION_PART_2,
    1,
)


KEEP_OLD = '"KEEP": 51,'
KEEP_NEW = '"KEEP": 52,'


if text.count(KEEP_OLD) != 1:
    raise RuntimeError(
        "DUNG: khong tim thay dung 1 "
        "KPI KEEP=51 trong dry-run goc."
    )


text = text.replace(
    KEEP_OLD,
    KEEP_NEW,
    1,
)


print()
print("=" * 126)
print("2. PATCH TRONG BO NHO")
print("=" * 126)

print(
    "Resolution SHA:",
    "CU -> MOI"
)

print(
    "KEEP KPI      :",
    "51 -> 52"
)

print(
    "Dry-run goc   : KHONG SUA FILE"
)

print(
    "Database      : CHUA GHI"
)


# ============================================================
# 4. CHAY DRY-RUN DA SUA TRONG BO NHO
# ============================================================

globals_run = {
    "__name__":
        "__main__",

    "__file__":
        str(SOURCE),
}


print()
print("=" * 126)
print("3. BAT DAU DRY-RUN TONG CUOI")
print("=" * 126)


exec(
    compile(
        text,
        str(SOURCE)
        + "<RAM_PATCH_KEEP52>",
        "exec",
    ),
    globals_run,
    globals_run,
)


# ============================================================
# 5. KIEM TRA FINGERPRINT MOI
# ============================================================

batch1 = (
    globals_run.get(
        "batch1"
    )
    or {}
)

fp = str(
    batch1.get(
        "batch_fingerprint"
    )
    or ""
)


print()
print("=" * 126)
print("4. KHOA FINGERPRINT MOI")
print("=" * 126)

print(
    "Fingerprint thực tế =",
    fp,
)

print(
    "Fingerprint yêu cầu =",
    EXPECTED_NEW_FP,
)


if fp != EXPECTED_NEW_FP:
    raise RuntimeError(
        "DUNG: fingerprint dry-run "
        "khong dung nen moi."
    )


if batch1.get("counts") != {
    "KEEP": 52,
    "DONE": 184,
    "READY": 5,
    "BLOCK": 0,
}:
    raise RuntimeError(
        "DUNG: KPI dry-run cuoi "
        "khong dung 52/184/5/0."
    )


if (
    batch1.get(
        "candidate_count"
    )
    != 5
):
    raise RuntimeError(
        "DUNG: candidate_count != 5."
    )


if (
    batch1.get(
        "effective_block_count"
    )
    != 0
):
    raise RuntimeError(
        "DUNG: effective blocker != 0."
    )


if (
    batch1.get(
        "ready_for_execution"
    )
    is not True
):
    raise RuntimeError(
        "DUNG: ready_for_execution "
        "khong True."
    )


# ============================================================
# 6. FILE THAT PHAI CON NGUYEN
# ============================================================

after = {
    "db":
        sha256(DB),

    "service":
        sha256(SERVICE),

    "lock":
        sha256(LOCK),

    "resolution":
        sha256(RESOLUTION),

    "roster":
        sha256(ROSTER),
}


if after != actual:
    raise RuntimeError(
        "DUNG: file that thay doi "
        "trong luc dry-run."
    )


print()
print("=" * 126)
print(
    "DRY-RUN CUOI SAU KEEP LUONG MINH: PASS"
)
print("=" * 126)

print(
    "KEEP/DONE/READY/BLOCK =",
    batch1.get("counts"),
)

print(
    "candidate_count       =",
    batch1.get(
        "candidate_count"
    ),
)

print(
    "effective_block_count =",
    batch1.get(
        "effective_block_count"
    ),
)

print(
    "ready_for_execution   =",
    batch1.get(
        "ready_for_execution"
    ),
)

print(
    "Batch fingerprint     =",
    fp,
)

print(
    "Mầm non Lượng Minh    = GIU NGUYEN"
)

print(
    "5 READY               = CHUA THUC HIEN THAT"
)

print(
    "Database              = KHONG THAY DOI"
)

print(
    "Service/Lock/Resolution/Roster = KHONG THAY DOI"
)

print("=" * 126)
