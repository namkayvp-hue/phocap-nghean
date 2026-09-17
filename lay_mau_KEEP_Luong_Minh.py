from __future__ import annotations

import json
import hashlib
import sys
from pathlib import Path

sys.dont_write_bytecode = True

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


ROOT = Path(r"C:\PhoCap")

LOCK = (
    ROOT
    / "data"
    / "school_merger_registry"
    / "qd3805_level_lock.json"
)

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


def sha256(path):
    h = hashlib.sha256()

    with path.open("rb") as f:
        for b in iter(
            lambda: f.read(1024 * 1024),
            b"",
        ):
            h.update(b)

    return h.hexdigest()


print("=" * 120)
print("LAY MAU KEEP THAT DE SUA LUONG MINH")
print("CHI DOC - KHONG SUA BAT KY FILE NAO")
print("=" * 120)

print("DB SHA         =", sha256(DB))
print("Service SHA    =", sha256(SERVICE))
print("Resolution SHA =", sha256(RESOLUTION))
print("Level lock SHA =", sha256(LOCK))


payload = json.loads(
    LOCK.read_text(
        encoding="utf-8-sig"
    )
)

operations = [
    dict(x)
    for x in (
        payload.get("operations")
        or []
    )
    if isinstance(x, dict)
]

orphans = [
    dict(x)
    for x in (
        payload.get("orphans")
        or []
    )
    if isinstance(x, dict)
]


# ============================================================
# 1. LUONG MINH ORPHAN
# ============================================================

lm = [
    x
    for x in orphans
    if (
        str(
            x.get("operation_id")
            or ""
        )
        == "QD3805-ORPHAN-R1216"
        and int(
            x.get("stt")
            or 0
        )
        == 1211
    )
]

print()
print("=" * 120)
print("1. LUONG MINH HIEN TAI")
print("=" * 120)

print(
    json.dumps(
        lm,
        ensure_ascii=False,
        indent=2,
    )
)


# ============================================================
# 2. LAY 5 MAU KEEP MN THAT
# ============================================================

mn_keep = [
    x
    for x in operations
    if (
        str(
            x.get("batch")
            or ""
        )
        == "GIỮ NGUYÊN"
        and "MN" in [
            str(v or "").upper()
            for v in (
                x.get("source_levels")
                or []
            )
        ]
    )
]


print()
print("=" * 120)
print("2. CAC MAU KEEP MN THAT")
print("=" * 120)

print(
    "So KEEP MN tim thay =",
    len(mn_keep),
)

for item in mn_keep[:5]:
    print()
    print(
        json.dumps(
            item,
            ensure_ascii=False,
            indent=2,
        )
    )


# ============================================================
# 3. TIM MAU GAN STT 1211 NHAT
# ============================================================

def first_stt(x):
    values = []

    for key in (
        "first_stt",
        "stt",
        "last_stt",
    ):
        try:
            if x.get(key) is not None:
                values.append(
                    int(float(x[key]))
                )
        except Exception:
            pass

    return (
        min(values)
        if values
        else 999999
    )


near = sorted(
    operations,
    key=lambda x: abs(
        first_stt(x) - 1211
    ),
)[:8]


print()
print("=" * 120)
print("3. CAC OPERATION GAN STT 1211")
print("=" * 120)

for item in near:
    print()
    print(
        json.dumps(
            item,
            ensure_ascii=False,
            indent=2,
        )
    )


# ============================================================
# 4. KPI HIEN TAI
# ============================================================

from app.services.school_merger_level_batch_service import (
    registry_level_summary,
    build_level_batch_preview,
)

summary = registry_level_summary(
    "MN"
)

preview = build_level_batch_preview(
    school_year_id=2,
    level_code="MN",
)


print()
print("=" * 120)
print("4. TRANG THAI HIEN TAI")
print("=" * 120)

print(
    "registry =",
    summary,
)

print(
    "counts   =",
    preview.get("counts"),
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
    "fingerprint           =",
    preview.get(
        "batch_fingerprint"
    ),
)


print()
print("=" * 120)
print("HOAN TAT - KHONG CO FILE NAO BI SUA")
print("=" * 120)
