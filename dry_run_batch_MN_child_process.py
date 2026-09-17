import sys
import json
import sqlite3
import hashlib
import shutil
import tempfile
import subprocess
from pathlib import Path
from collections import defaultdict

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

EXPECTED = {
    "QD3805-OP-0175",
    "QD3805-OP-0337",
    "QD3805-OP-0410",
    "QD3805-OP-0449",
    "QD3805-OP-0592",
    "QD3805-OP-0600",
}

PLAN_TO_OP = {
    "PA2026-785CDDA8D8CC": "QD3805-OP-0175",
    "PA2026-E494BD00A794": "QD3805-OP-0337",
    "PA2026-43804C58D423": "QD3805-OP-0410",
    "PA2026-4AB75BCD93EB": "QD3805-OP-0449",
    "PA2026-7802B1BD1912": "QD3805-OP-0592",
    "PA2026-1E90C6AAFD47": "QD3805-OP-0600",
}

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
reg_before = registry_hashes()

# ============================================================
# LẤY DỮ LIỆU SNAPSHOT MN
# ============================================================

con = sqlite3.connect(
    DB.resolve().as_uri() + "?mode=ro",
    uri=True,
)
con.row_factory = sqlite3.Row
con.execute("PRAGMA query_only=ON")

years = con.execute(
    "SELECT id,code FROM school_years"
).fetchall()

def year_id(code):
    for r in years:
        value = (
            str(r["code"] or "")
            .replace("–", "-")
            .replace("—", "-")
            .strip()
        )
        if value == code:
            return int(r["id"])
    return None

y2526 = year_id("2025-2026")
y2627 = year_id("2026-2027")

if y2526 is None or y2627 is None:
    raise RuntimeError(
        "Không tìm thấy đủ 2 năm học."
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
      AND UPPER(
          TRIM(
              COALESCE(syr.source_level,'')
          )
      )='MN'

    ORDER BY syr.school_id, syr.id
    """,
    (y2526,),
).fetchall()

con.close()

mn_rows = []

for i, raw in enumerate(rows, 1):
    r = dict(raw)

    code = str(
        r.get("ministry_staff_code") or ""
    ).strip()

    if not code:
        raise RuntimeError(
            "Có dòng MN thiếu mã Bộ."
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

print("=" * 120)
print("DRY-RUN BATCH MN TRONG TIẾN TRÌNH MỚI")
print("=" * 120)
print("Snapshot rows   :", len(mn_rows))
print("Snapshot schools:", school_count)

# ============================================================
# CHILD PROCESS
# Registry tạm được gắn TRƯỚC audit đầu tiên.
# ============================================================

child_code = r'''
import sys
import json
from pathlib import Path

tmpdir = Path(sys.argv[1])
year_id = int(sys.argv[2])

# Import audit service trước.
import app.services.school_merger_source_audit_service as audit_svc

# Gắn registry tạm trước bất kỳ audit nào.
audit_svc.SOURCE_ROSTER_DIR = tmpdir

# Sau đó mới import preview/batch.
import app.services.school_merger_preview_service as preview_svc
import app.services.school_merger_level_batch_service as batch_svc

# Ép các symbol đã import trực tiếp về đúng audit service
# trong tiến trình hiện tại.
if hasattr(batch_svc, "audit_official_plans"):
    batch_svc.audit_official_plans = (
        audit_svc.audit_official_plans
    )

if hasattr(
    preview_svc,
    "audit_official_plan_source"
):
    preview_svc.audit_official_plan_source = (
        audit_svc.audit_official_plan_source
    )

if hasattr(
    preview_svc,
    "audit_official_plans"
):
    preview_svc.audit_official_plans = (
        audit_svc.audit_official_plans
    )

# ------------------------------------------------------------
# 1. Kiểm chứng registry thực sự thấy 2 dataset
# ------------------------------------------------------------

summary = audit_svc.source_registry_summary()

# ------------------------------------------------------------
# 2. Audit MN trực tiếp trong child
# ------------------------------------------------------------

audit = audit_svc.audit_official_plans(
    school_year_id=year_id,
    commune_id=None,
    level_code="MN",
)

# ------------------------------------------------------------
# 3. Batch preview
# ------------------------------------------------------------

preview = batch_svc.build_level_batch_preview(
    school_year_id=year_id,
    level_code="MN",
)

# ------------------------------------------------------------
# Thu state theo operation
# ------------------------------------------------------------

states = {}

for row in preview.get("rows") or []:
    if not isinstance(row, dict):
        continue

    op = str(
        row.get("qd3805_operation_id") or ""
    ).strip()

    if not op:
        continue

    state = str(
        row.get("batch_state") or ""
    ).upper().strip()

    if op not in states:
        states[op] = state
    elif states[op] != state:
        states[op] = "BLOCK"

# Audit map theo plan_id
audit_by_plan = {}

for row in audit.get("rows") or []:
    plan = row.get("plan") or {}
    a = row.get("audit") or {}

    pid = str(plan.get("id") or "")

    if pid:
        audit_by_plan[pid] = {
            "pass": a.get("pass"),
            "status": a.get("status"),
            "blockers": a.get("blockers") or [],
        }

out = {
    "registry_summary": summary,
    "audit_total": audit.get("total"),
    "audit_pass_count": audit.get("pass_count"),
    "audit_block_count": audit.get("block_count"),
    "audit_by_plan": audit_by_plan,
    "counts": preview.get("counts") or {},
    "candidate_count": preview.get("candidate_count"),
    "effective_block_count": preview.get(
        "effective_block_count"
    ),
    "ready_for_execution": preview.get(
        "ready_for_execution"
    ),
    "states": states,
    "extra_blockers": preview.get(
        "extra_blockers"
    ) or [],
    "candidates": preview.get("candidates") or [],
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
    prefix="MN_BATCH_CHILD_"
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
            default=str,
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
            "Tiến trình dry-run con bị lỗi."
        )

    payload = json.loads(
        proc.stdout.strip()
    )

# ============================================================
# IN KẾT QUẢ
# ============================================================

print()
print("=" * 120)
print("REGISTRY TRONG CHILD")
print("=" * 120)

summary = payload.get(
    "registry_summary"
) or {}

print(
    "dataset_count:",
    summary.get("dataset_count"),
)

for d in summary.get("datasets") or []:
    print(
        " -",
        d.get("dataset_id"),
        "|",
        d.get("level_code"),
        "| rows =",
        d.get("row_count"),
    )

print()
print("=" * 120)
print("AUDIT 6 OPERATION TRONG CHILD")
print("=" * 120)

audit_by_plan = payload.get(
    "audit_by_plan"
) or {}

for pid, op in PLAN_TO_OP.items():

    a = audit_by_plan.get(pid) or {}

    print()
    print(op)
    print(
        "  audit pass :",
        a.get("pass"),
    )
    print(
        "  status     :",
        a.get("status"),
    )

    for x in a.get("blockers") or []:
        print("  -", x)

print()
print("=" * 120)
print("KPI BATCH TRONG CHILD")
print("=" * 120)

print(
    "counts =",
    json.dumps(
        payload.get("counts") or {},
        ensure_ascii=False,
    )
)

print(
    "candidate_count       =",
    payload.get("candidate_count"),
)

print(
    "effective_block_count =",
    payload.get("effective_block_count"),
)

print(
    "ready_for_execution   =",
    payload.get("ready_for_execution"),
)

print()
print("=" * 120)
print("TRẠNG THÁI 6 OPERATION")
print("=" * 120)

states = payload.get("states") or {}

for op in sorted(EXPECTED):
    print(
        op,
        "=",
        states.get(op),
    )

print()
print(
    "QD3805-OP-0338 =",
    states.get("QD3805-OP-0338"),
)

print()
print("=" * 120)
print("EXTRA BLOCKERS CỦA BATCH")
print("=" * 120)

extra = payload.get(
    "extra_blockers"
) or []

if not extra:
    print("<KHÔNG CÓ>")
else:
    for item in extra:
        print(
            json.dumps(
                item,
                ensure_ascii=False,
                default=str,
            )
        )

# ============================================================
# AN TOÀN
# ============================================================

db_after = sha256(DB)
reg_after = registry_hashes()

print()
print("=" * 120)
print("KIỂM TRA AN TOÀN")
print("=" * 120)

print("DB hash trước:", db_before)
print("DB hash sau  :", db_after)

if db_before != db_after:
    raise RuntimeError(
        "DỪNG: database thay đổi."
    )

if reg_before != reg_after:
    raise RuntimeError(
        "DỪNG: registry thật thay đổi."
    )

print("Database      : KHÔNG THAY ĐỔI")
print("Registry thật : KHÔNG THAY ĐỔI")
print("Registry tạm  : ĐÃ TỰ XÓA")
print("=" * 120)
