import sys
import json
import sqlite3
import hashlib
import shutil
import tempfile
import subprocess
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(r"C:\PhoCap")
DB = ROOT / "data" / "phocap.db"

REAL_ROSTER_DIR = (
    ROOT / "data" / "school_merger_source_rosters"
)

TH_JSON = REAL_ROSTER_DIR / "TH_2025_2026.json"

EXPECTED_DB_SHA = (
    "44b1aa841cdd76301c57d9fc601121ae"
    "96f9312084ef05959eaae54acf17c8c9"
)

EXPECTED_READY = {
    "QD3805-OP-0175",
    "QD3805-OP-0410",
    "QD3805-OP-0449",
    "QD3805-OP-0592",
    "QD3805-OP-0600",
}

OP0337 = "QD3805-OP-0337"
OP0338 = "QD3805-OP-0338"

def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            b = f.read(1024 * 1024)
            if not b:
                break
            h.update(b)
    return h.hexdigest()

def registry_hashes():
    out = {}
    if REAL_ROSTER_DIR.exists():
        for p in sorted(REAL_ROSTER_DIR.glob("*.json")):
            out[p.name] = sha256(p)
    return out

def fmt_date(v):
    s = str(v or "").strip()

    if (
        len(s) >= 10
        and s[4] == "-"
        and s[7] == "-"
    ):
        return (
            s[8:10]
            + "/"
            + s[5:7]
            + "/"
            + s[0:4]
        )

    return s

def position_label(group, title):
    g = str(group or "").strip().upper()

    if g == "CBQL":
        return "Cán bộ quản lý"

    if g == "GIAO_VIEN":
        return "Giáo viên"

    if g == "NHAN_VIEN":
        return "Nhân viên"

    return str(title or group or "").strip()

db_before = sha256(DB)
registry_before = registry_hashes()

print("=" * 120)
print("DRY-RUN CUOI OP-0337 - PRECOMPLETED NHIEU NGUON")
print("KHONG SUA SOURCE - KHONG SUA REGISTRY THAT - KHONG GHI DB")
print("=" * 120)

print("DB SHA:", db_before)

if db_before != EXPECTED_DB_SHA:
    raise RuntimeError(
        "DUNG: DB hash khong con dung nen sau khi don 51394."
    )

# ============================================================
# Tao snapshot MN 2025-2026 tam
# ============================================================

con = sqlite3.connect(
    DB.resolve().as_uri() + "?mode=ro",
    uri=True,
)
con.row_factory = sqlite3.Row
con.execute("PRAGMA query_only=ON")

years = {
    str(r["code"] or "")
    .replace("–", "-")
    .replace("—", "-")
    .strip(): int(r["id"])
    for r in con.execute(
        "SELECT id,code FROM school_years"
    ).fetchall()
}

y2526 = years.get("2025-2026")
y2627 = years.get("2026-2027")

if y2526 is None or y2627 is None:
    raise RuntimeError(
        "Khong tim thay du nam hoc."
    )

rows = con.execute(
    """
    SELECT
        syr.id,
        syr.school_id,
        syr.status_code,
        syr.position_group,
        syr.position_title,
        syr.source_status_label,

        sm.ministry_staff_code,
        sm.full_name,
        sm.date_of_birth,
        sm.gender,

        s.name AS school_name,
        c.name AS commune_name

    FROM staff_year_records syr

    JOIN staff_members sm
      ON sm.id=syr.staff_member_id

    JOIN schools s
      ON s.id=syr.school_id

    JOIN communes c
      ON c.id=s.commune_id

    WHERE syr.school_year_id=?
      AND UPPER(TRIM(COALESCE(syr.source_level,'')))='MN'

    ORDER BY syr.school_id,syr.id
    """,
    (y2526,),
).fetchall()

mn_rows = []

for i, raw in enumerate(rows, 1):
    r = dict(raw)

    code = str(
        r.get("ministry_staff_code") or ""
    ).strip()

    if not code:
        raise RuntimeError(
            "Snapshot MN 2025-2026 co dong thieu ma Bo."
        )

    mn_rows.append({
        "excel_row": i,
        "commune_name": str(
            r.get("commune_name") or ""
        ).strip(),
        "school_name": str(
            r.get("school_name") or ""
        ).strip(),
        "staff_code": code,
        "full_name": str(
            r.get("full_name") or ""
        ).strip(),
        "date_of_birth": fmt_date(
            r.get("date_of_birth")
        ),
        "gender": str(
            r.get("gender") or ""
        ).strip(),
        "status_label": str(
            r.get("source_status_label")
            or r.get("status_code")
            or ""
        ).strip(),
        "position_label": position_label(
            r.get("position_group"),
            r.get("position_title"),
        ),
    })

school_count = len({
    (
        x["commune_name"],
        x["school_name"],
    )
    for x in mn_rows
})

dataset = {
    "version": 1,
    "dataset_id": "MN-2025-2026-DB-SNAPSHOT-DRYRUN",
    "level_code": "MN",
    "school_year_code": "2025-2026",
    "source_file": (
        "INTERNAL_DB_SNAPSHOT:"
        "phocap.db/staff_year_records"
    ),
    "source_sha256": db_before,
    "row_count": len(mn_rows),
    "school_count": school_count,
    "active_status_labels": [
        "Đang làm việc",
        "Chuyển đến",
    ],
    "rows": mn_rows,
}

con.close()

print(
    "Snapshot MN:",
    len(mn_rows),
    "rows /",
    school_count,
    "schools",
)

# ============================================================
# Child process: patch trong RAM
# ============================================================

child_code = r'''
import sys
import json
from pathlib import Path

tmpdir = Path(sys.argv[1])
year_id = int(sys.argv[2])

import app.services.school_merger_source_audit_service as audit_svc

audit_svc.SOURCE_ROSTER_DIR = tmpdir

import app.services.school_merger_preview_service as preview_svc
import app.services.school_merger_level_batch_service as batch_svc

if hasattr(batch_svc, "audit_official_plans"):
    batch_svc.audit_official_plans = (
        audit_svc.audit_official_plans
    )

if hasattr(preview_svc, "audit_official_plan_source"):
    preview_svc.audit_official_plan_source = (
        audit_svc.audit_official_plan_source
    )

if hasattr(preview_svc, "audit_official_plans"):
    preview_svc.audit_official_plans = (
        audit_svc.audit_official_plans
    )

original_precompleted = (
    batch_svc._precompleted_resolution_status
)

def op0337_precompleted(
    *,
    operation_id,
    resolution,
    audit_item=None,
):
    if str(operation_id or "") != "QD3805-OP-0337":
        return original_precompleted(
            operation_id=operation_id,
            resolution=resolution,
            audit_item=audit_item,
        )

    source_codes = [
        "40429325",
        "40429332",
    ]

    target_code = "40429310"

    expected_previous = {
        "40429310": 29,
        "40429325": 25,
        "40429332": 33,
    }

    con = batch_svc.engine._connect(
        read_only=True
    )

    try:
        schools = {}

        for code in [
            target_code,
            *source_codes,
        ]:
            row = con.execute(
                """
                SELECT id,code,name,is_active
                FROM schools
                WHERE code=?
                LIMIT 1
                """,
                (code,),
            ).fetchone()

            if row is None:
                return {
                    "pass": False,
                    "operation_id": operation_id,
                    "reason": (
                        "Khong tim thay du truong "
                        "nguon/dich."
                    ),
                }

            schools[code] = dict(row)

        year_rows = con.execute(
            """
            SELECT id,code
            FROM school_years
            WHERE code IN ('2025-2026','2026-2027')
            """
        ).fetchall()

        year_ids = {
            str(x["code"]): int(x["id"])
            for x in year_rows
        }

        py = year_ids["2025-2026"]
        cy = year_ids["2026-2027"]

        previous_rows = con.execute(
            """
            SELECT
                staff_member_id,
                school_id,
                status_code,
                is_active
            FROM staff_year_records
            WHERE school_year_id=?
              AND school_id IN (
                  ?,?,?
              )
            """,
            (
                py,
                int(schools[target_code]["id"]),
                int(schools[source_codes[0]]["id"]),
                int(schools[source_codes[1]]["id"]),
            ),
        ).fetchall()

        previous_ids = {
            int(x["staff_member_id"])
            for x in previous_rows
            if int(x["is_active"] or 0) == 1
            and str(x["status_code"] or "")
                == "DANG_LAM_VIEC"
        }

        current_target_rows = con.execute(
            """
            SELECT staff_member_id
            FROM staff_year_records
            WHERE school_year_id=?
              AND school_id=?
              AND is_active=1
            """,
            (
                cy,
                int(schools[target_code]["id"]),
            ),
        ).fetchall()

        current_target_ids = {
            int(x["staff_member_id"])
            for x in current_target_rows
        }

        current_source_total = int(
            con.execute(
                """
                SELECT COUNT(*)
                FROM staff_year_records
                WHERE school_year_id=?
                  AND school_id IN (?,?)
                """,
                (
                    cy,
                    int(
                        schools[
                            source_codes[0]
                        ]["id"]
                    ),
                    int(
                        schools[
                            source_codes[1]
                        ]["id"]
                    ),
                ),
            ).fetchone()[0]
        )

    finally:
        con.close()

    audit = dict(audit_item or {})

    school_checks = [
        dict(x)
        for x in (
            audit.get("school_checks") or []
        )
        if isinstance(x, dict)
    ]

    audit_counts = {}

    for code in [
        target_code,
        *source_codes,
    ]:
        item = next(
            (
                x for x in school_checks
                if str(
                    x.get("school_code") or ""
                ).strip() == code
            ),
            None,
        )

        audit_counts[code] = (
            int(
                item.get(
                    "active_db_eligible"
                ) or 0
            )
            if item is not None
            else -1
        )

    checks = {
        "audit_pass":
            bool(audit.get("pass")) is True,

        "target_active":
            bool(
                schools[
                    target_code
                ]["is_active"]
            ) is True,

        "source_1_inactive":
            bool(
                schools[
                    source_codes[0]
                ]["is_active"]
            ) is False,

        "source_2_inactive":
            bool(
                schools[
                    source_codes[1]
                ]["is_active"]
            ) is False,

        "previous_target_eligible":
            audit_counts[target_code]
            == expected_previous[target_code],

        "previous_source_1_eligible":
            audit_counts[source_codes[0]]
            == expected_previous[source_codes[0]],

        "previous_source_2_eligible":
            audit_counts[source_codes[1]]
            == expected_previous[source_codes[1]],

        "previous_union_87":
            len(previous_ids) == 87,

        "current_target_87":
            len(current_target_ids) == 87,

        "identity_exact":
            current_target_ids
            == previous_ids,

        "current_sources_zero":
            current_source_total == 0,
    }

    return {
        "pass": all(checks.values()),
        "operation_id": operation_id,
        "rule": {
            "source_school_codes":
                source_codes,
            "target_school_code":
                target_code,
            "expected_previous_target_active":
                29,
            "expected_previous_source_active":
                [25,33],
            "expected_current_target_active":
                87,
            "expected_current_source_active":
                0,
        },
        "evidence": {
            "audit_counts":
                audit_counts,
            "previous_union_count":
                len(previous_ids),
            "current_target_count":
                len(current_target_ids),
            "current_source_total":
                current_source_total,
            "identity_exact":
                current_target_ids
                == previous_ids,
        },
        "checks": checks,
        "reason": (
            "Hai nguon da khoa; audit PASS; "
            "87 identity hien tai tai dich khop "
            "100% voi union eligible 2025-2026."
            if all(checks.values())
            else
            "Chua du bang chung precompleted."
        ),
    }

batch_svc._precompleted_resolution_status = (
    op0337_precompleted
)

# Resolution that only exists in child RAM.
orig_resolution_context = (
    batch_svc._resolution_context
)

def patched_resolution_context(level_code):
    ctx = orig_resolution_context(level_code)

    if str(level_code or "").upper() == "MN":
        payload = dict(
            ctx.get("payload") or {}
        )

        pre = list(
            payload.get("precompleted") or []
        )

        pre.append({
            "operation_id":
                "QD3805-OP-0337",
            "source_school_codes": [
                "40429325",
                "40429332",
            ],
            "target_school_code":
                "40429310",
        })

        payload["precompleted"] = pre

        ctx = dict(ctx)
        ctx["payload"] = payload
        ctx["precompleted"] = pre

    return ctx

batch_svc._resolution_context = (
    patched_resolution_context
)

preview = (
    batch_svc.build_level_batch_preview(
        school_year_id=year_id,
        level_code="MN",
    )
)

states = {}

precompleted_evidence = None

for row in preview.get("rows") or []:
    if not isinstance(row, dict):
        continue

    op = str(
        row.get("qd3805_operation_id")
        or ""
    ).strip()

    state = str(
        row.get("batch_state")
        or ""
    ).upper().strip()

    if op:
        states[op] = state

    if op == "QD3805-OP-0337":
        plan = row.get("plan") or row
        precompleted_evidence = (
            plan.get(
                "qd3805_precompleted"
            )
            or row.get(
                "qd3805_precompleted"
            )
        )

out = {
    "counts":
        preview.get("counts") or {},
    "candidate_count":
        preview.get("candidate_count"),
    "effective_block_count":
        preview.get(
            "effective_block_count"
        ),
    "ready_for_execution":
        preview.get(
            "ready_for_execution"
        ),
    "states":
        states,
    "extra_blockers":
        preview.get(
            "extra_blockers"
        ) or [],
    "op0337_precompleted":
        precompleted_evidence,
}

print(
    json.dumps(
        out,
        ensure_ascii=True,
        default=str,
    )
)
'''

with tempfile.TemporaryDirectory(
    prefix="MN_OP0337_FINAL_DRYRUN_"
) as tmp:

    tmpdir = Path(tmp)

    shutil.copy2(
        TH_JSON,
        tmpdir / "TH_2025_2026.json",
    )

    (
        tmpdir / "MN_2025_2026.json"
    ).write_text(
        json.dumps(
            dataset,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            child_code,
            str(tmpdir),
            str(y2627),
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr)

        raise RuntimeError(
            "Child dry-run bi loi."
        )

    payload = json.loads(
        proc.stdout.strip()
    )

print()
print("=" * 120)
print("KPI SAU DRY-RUN")
print("=" * 120)

print(
    json.dumps(
        payload["counts"],
        ensure_ascii=False,
    )
)

print(
    "candidate_count       =",
    payload.get("candidate_count"),
)

print(
    "effective_block_count =",
    payload.get(
        "effective_block_count"
    ),
)

print(
    "ready_for_execution   =",
    payload.get(
        "ready_for_execution"
    ),
)

print()
print("=" * 120)
print("TRANG THAI CAC OPERATION CHINH")
print("=" * 120)

states = payload.get("states") or {}

print(
    "QD3805-OP-0337 =",
    states.get("QD3805-OP-0337"),
)

for op in sorted(EXPECTED_READY):
    print(
        op,
        "=",
        states.get(op),
    )

print(
    "QD3805-OP-0338 =",
    states.get("QD3805-OP-0338"),
)

print()
print("=" * 120)
print("BANG CHUNG PRECOMPLETED OP-0337")
print("=" * 120)

print(
    json.dumps(
        payload.get(
            "op0337_precompleted"
        ),
        ensure_ascii=False,
        indent=2,
    )
)

print()
print("=" * 120)
print("EXTRA BLOCKERS")
print("=" * 120)

for item in (
    payload.get("extra_blockers") or []
):
    print(
        json.dumps(
            item,
            ensure_ascii=False,
        )
    )

# ============================================================
# Ky vong
# ============================================================

expected_counts = {
    "KEEP": 51,
    "DONE": 183,
    "READY": 5,
    "BLOCK": 1,
}

if payload.get("counts") != expected_counts:
    raise RuntimeError(
        "KPI khong dung ky vong: "
        + json.dumps(
            payload.get("counts"),
            ensure_ascii=False,
        )
    )

if states.get(OP0337) != "DONE":
    raise RuntimeError(
        "OP-0337 chua thanh DONE."
    )

if states.get(OP0338) != "BLOCK":
    raise RuntimeError(
        "OP-0338 khong con BLOCK ngoai du kien."
    )

for op in EXPECTED_READY:
    if states.get(op) != "READY":
        raise RuntimeError(
            f"{op} khong READY."
        )

if (
    payload.get(
        "effective_block_count"
    )
    != 2
):
    raise RuntimeError(
        "effective_block_count khong bang 2."
    )

# ============================================================
# Safety
# ============================================================

db_after = sha256(DB)
registry_after = registry_hashes()

print()
print("=" * 120)
print("KIEM TRA AN TOAN")
print("=" * 120)

print("DB SHA truoc:", db_before)
print("DB SHA sau  :", db_after)

if db_before != db_after:
    raise RuntimeError(
        "DUNG: DB da thay doi."
    )

if registry_before != registry_after:
    raise RuntimeError(
        "DUNG: registry that da thay doi."
    )

print("Database      : KHONG THAY DOI")
print("Registry that : KHONG THAY DOI")
print("Source code   : KHONG THAY DOI")
print("Registry tam  : DA TU XOA")

print("=" * 120)
