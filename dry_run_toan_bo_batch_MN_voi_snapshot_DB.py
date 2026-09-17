import sys
import json
import sqlite3
import hashlib
import shutil
import tempfile
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

EXPECTED_READY = {
    "QD3805-OP-0175",
    "QD3805-OP-0337",
    "QD3805-OP-0410",
    "QD3805-OP-0449",
    "QD3805-OP-0592",
    "QD3805-OP-0600",
}

SPECIAL_BLOCK = "QD3805-OP-0338"


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            b = f.read(1024 * 1024)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def snapshot_real_registry():
    result = {}
    if REAL_ROSTER_DIR.exists():
        for p in sorted(REAL_ROSTER_DIR.glob("*.json")):
            result[p.name] = sha256(p)
    return result


def fmt_date(v):
    s = str(v or "").strip()

    if not s:
        return ""

    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        return f"{s[8:10]}/{s[5:7]}/{s[0:4]}"

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


def operation_states(preview):
    grouped = defaultdict(set)

    for row in preview.get("rows") or []:
        if not isinstance(row, dict):
            continue

        op_id = str(
            row.get("qd3805_operation_id") or ""
        ).strip()

        if not op_id:
            continue

        grouped[op_id].add(
            str(
                row.get("batch_state") or "BLOCK"
            ).upper().strip()
        )

    out = {}

    for op_id, states in grouped.items():
        if len(states) == 1:
            out[op_id] = next(iter(states))
        else:
            # Trường hợp mapping bất thường thì coi là BLOCK.
            out[op_id] = "BLOCK"

    return out


db_before = sha256(DB)
registry_before = snapshot_real_registry()

print("=" * 120)
print("DRY-RUN TOÀN BỘ BATCH MN VỚI SNAPSHOT DB 2025-2026")
print("KHÔNG CÀI REGISTRY - KHÔNG SÁP NHẬP - KHÔNG GHI DATABASE")
print("=" * 120)

# ============================================================
# 1. LẤY NĂM VÀ DỰNG SNAPSHOT MN
# ============================================================

con = sqlite3.connect(
    DB.resolve().as_uri() + "?mode=ro",
    uri=True,
    timeout=30,
)

con.row_factory = sqlite3.Row
con.execute("PRAGMA query_only=ON")

years = con.execute(
    "SELECT id,code FROM school_years"
).fetchall()

def get_year(code):
    return next(
        (
            r for r in years
            if str(r["code"] or "")
            .replace("–", "-")
            .replace("—", "-")
            .strip()
            == code
        ),
        None,
    )

y2526 = get_year("2025-2026")
y2627 = get_year("2026-2027")

if y2526 is None or y2627 is None:
    raise RuntimeError(
        "Không tìm thấy đủ năm học 2025-2026 / 2026-2027."
    )

raw_rows = con.execute(
    """
    SELECT
        syr.id,
        syr.school_id,
        syr.status_code,
        syr.position_group,
        syr.position_title,
        syr.source_level,
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

    ORDER BY syr.school_id, syr.id
    """,
    (int(y2526["id"]),),
).fetchall()

con.close()

mn_rows = []

for idx, raw in enumerate(raw_rows, 1):
    r = dict(raw)

    code = str(
        r.get("ministry_staff_code") or ""
    ).strip()

    if not code:
        raise RuntimeError(
            "Snapshot MN có dòng thiếu ministry_staff_code."
        )

    mn_rows.append({
        "excel_row": idx,
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
    "dataset_id": "MN-2025-2026-DB-SNAPSHOT",
    "level_code": "MN",
    "school_year_code": "2025-2026",

    # Ghi rõ nguồn nội bộ, không giả danh Excel.
    "source_file": (
        "INTERNAL_DB_SNAPSHOT:"
        "phocap.db/staff_year_records"
    ),
    "source_sha256": db_before,

    "row_count": len(mn_rows),
    "school_count": school_count,
    "rows": mn_rows,
}

print("Snapshot MN rows   :", len(mn_rows))
print("Snapshot MN schools:", school_count)

# ============================================================
# 2. PREVIEW HIỆN TẠI
# ============================================================

import app.services.school_merger_source_audit_service as audit_svc

from app.services.school_merger_level_batch_service import (
    build_level_batch_preview,
)

before = build_level_batch_preview(
    school_year_id=int(y2627["id"]),
    level_code="MN",
)

before_states = operation_states(before)

print()
print("KPI TRƯỚC:")
print(
    json.dumps(
        before.get("counts") or {},
        ensure_ascii=False,
    )
)
print(
    "BLOCK hiệu lực trước:",
    before.get("effective_block_count"),
)

# ============================================================
# 3. PREVIEW VỚI REGISTRY TẠM
# ============================================================

original_dir = audit_svc.SOURCE_ROSTER_DIR

with tempfile.TemporaryDirectory(
    prefix="MN_FULL_BATCH_DRYRUN_"
) as tmp:

    tmpdir = Path(tmp)

    # Giữ nguyên TH registry hiện tại.
    shutil.copy2(
        TH_JSON,
        tmpdir / "TH_2025_2026.json",
    )

    temp_mn = tmpdir / "MN_2025_2026.json"

    temp_mn.write_text(
        json.dumps(
            dataset,
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )

    audit_svc.SOURCE_ROSTER_DIR = tmpdir

    try:
        after = build_level_batch_preview(
            school_year_id=int(y2627["id"]),
            level_code="MN",
        )
    finally:
        audit_svc.SOURCE_ROSTER_DIR = original_dir

after_states = operation_states(after)

print()
print("KPI SAU DRY-RUN:")
print(
    json.dumps(
        after.get("counts") or {},
        ensure_ascii=False,
    )
)
print(
    "BLOCK hiệu lực sau:",
    after.get("effective_block_count"),
)

print(
    "Candidate MN sau:",
    len(after.get("candidates") or [])
)

# ============================================================
# 4. SO SÁNH MỌI OPERATION
# ============================================================

print()
print("=" * 120)
print("OPERATION CÓ THAY ĐỔI TRẠNG THÁI")
print("=" * 120)

changed = []

for op_id in sorted(
    set(before_states) | set(after_states)
):
    b = before_states.get(op_id, "<KHÔNG CÓ>")
    a = after_states.get(op_id, "<KHÔNG CÓ>")

    if b != a:
        changed.append((op_id, b, a))
        print(
            f"{op_id}: {b}  -->  {a}"
        )

print()
print("Tổng operation đổi trạng thái:", len(changed))

# ============================================================
# 5. KHÓA KỲ VỌNG
# ============================================================

print()
print("=" * 120)
print("KIỂM TRA KỲ VỌNG")
print("=" * 120)

counts = after.get("counts") or {}

if (
    int(counts.get("KEEP") or 0) != 51
    or int(counts.get("DONE") or 0) != 182
    or int(counts.get("READY") or 0) != 6
    or int(counts.get("BLOCK") or 0) != 1
):
    raise RuntimeError(
        "KPI sau dry-run không đúng kỳ vọng "
        "51 KEEP / 182 DONE / 6 READY / 1 BLOCK: "
        + json.dumps(
            counts,
            ensure_ascii=False,
        )
    )

actual_changed = {
    op_id
    for op_id, b, a in changed
    if b == "BLOCK" and a == "READY"
}

if actual_changed != EXPECTED_READY:
    raise RuntimeError(
        "Không phải đúng 6 operation dự kiến chuyển BLOCK -> READY.\n"
        "Thực tế: "
        + json.dumps(
            sorted(actual_changed),
            ensure_ascii=False,
        )
    )

for op_id in EXPECTED_READY:
    if after_states.get(op_id) != "READY":
        raise RuntimeError(
            f"{op_id} chưa READY."
        )

if after_states.get(SPECIAL_BLOCK) != "BLOCK":
    raise RuntimeError(
        "OP-0338 SPECIAL phải tiếp tục BLOCK."
    )

if int(after.get("effective_block_count") or 0) != 2:
    raise RuntimeError(
        "BLOCK hiệu lực phải còn đúng 2 "
        "(OP-0338 + 1 orphan chưa xác định)."
    )

print("ĐẠT:")
print("  - 182 DONE giữ nguyên.")
print("  - Đúng 6 MAPPED chuyển BLOCK -> READY.")
print("  - OP-0338 SPECIAL vẫn BLOCK.")
print("  - 1 orphan vẫn giữ CHẶN.")
print("  - BLOCK hiệu lực còn đúng 2.")

# ============================================================
# 6. AN TOÀN FILE THẬT
# ============================================================

db_after = sha256(DB)
registry_after = snapshot_real_registry()

print()
print("=" * 120)
print("KIỂM TRA AN TOÀN")
print("=" * 120)

print("DB hash trước:", db_before)
print("DB hash sau  :", db_after)

if db_before != db_after:
    raise RuntimeError(
        "DỪNG: phocap.db thay đổi."
    )

if registry_before != registry_after:
    raise RuntimeError(
        "DỪNG: source registry thật đã thay đổi."
    )

print("Database      : KHÔNG THAY ĐỔI")
print("Registry thật : KHÔNG THAY ĐỔI")
print("Snapshot tạm  : ĐÃ TỰ XÓA")
print("=" * 120)
