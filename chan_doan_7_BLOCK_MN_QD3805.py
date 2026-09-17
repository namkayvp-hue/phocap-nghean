import sys
import json
import sqlite3
import hashlib
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(r"C:\PhoCap")
DB = ROOT / "data" / "phocap.db"
OUT = ROOT / "exports" / "chan_doan_7_BLOCK_MN_QD3805.json"

def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()

db_before = sha256(DB)

# Chỉ đọc DB để lấy đúng ID năm học 2026-2027.
con = sqlite3.connect(
    DB.resolve().as_uri() + "?mode=ro",
    uri=True,
    timeout=30,
)
con.row_factory = sqlite3.Row
con.execute("PRAGMA query_only=ON")

years = con.execute(
    "SELECT id, code FROM school_years"
).fetchall()

con.close()

year = next(
    (
        r for r in years
        if str(r["code"] or "")
        .replace("–", "-")
        .replace("—", "-")
        .strip()
        == "2026-2027"
    ),
    None,
)

if year is None:
    raise SystemExit("Không tìm thấy năm học 2026-2027.")

from app.services.school_merger_level_batch_service import (
    build_level_batch_preview,
)

preview = build_level_batch_preview(
    school_year_id=int(year["id"]),
    level_code="MN",
)

counts = preview.get("counts") or {}
rows = preview.get("rows") or []
registry = preview.get("registry") or {}

blocks = []

for row in rows:
    if not isinstance(row, dict):
        continue

    if str(row.get("batch_state") or "").upper() != "BLOCK":
        continue

    audit = row.get("source_audit") or {}

    item = {
        "operation_id": str(
            row.get("qd3805_operation_id") or ""
        ),
        "plan_id": str(row.get("id") or ""),
        "commune": str(
            row.get("commune_excel")
            or row.get("commune")
            or ""
        ),
        "batch_state": row.get("batch_state"),
        "batch_label": row.get("batch_label"),
        "execution_status": row.get("execution_status"),
        "action_type": row.get("action_type"),
        "match_status": row.get("match_status"),
        "match_label": row.get("match_label"),
        "batch_blockers": list(
            row.get("batch_blockers") or []
        ),
        "audit_pass": audit.get("pass"),
        "audit_blockers": list(
            audit.get("blockers") or []
        ),
    }

    blocks.append(item)

# Gom operation duy nhất.
by_op = {}

for item in blocks:
    op_id = item["operation_id"] or "<KHÔNG CÓ OP_ID>"
    by_op.setdefault(op_id, []).append(item)

unresolved = list(
    registry.get("unresolved_orphans") or []
)

missing_ops = list(
    registry.get("missing_action_ops") or []
)

duplicates = list(
    registry.get("duplicate_mappings") or []
)

payload = {
    "school_year_id": int(year["id"]),
    "school_year_code": str(year["code"]),
    "counts": counts,
    "effective_block_count": preview.get(
        "effective_block_count"
    ),
    "block_operation_count": len(by_op),
    "blocks": blocks,
    "unresolved_orphans": unresolved,
    "missing_action_ops": missing_ops,
    "duplicate_mappings": duplicates,
}

OUT.parent.mkdir(parents=True, exist_ok=True)

OUT.write_text(
    json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
        default=str,
    ),
    encoding="utf-8",
)

print("=" * 118)
print("CHẨN ĐOÁN 7 BLOCK MẦM NON QĐ3805")
print("CHỈ ĐỌC - KHÔNG THỰC HIỆN SÁP NHẬP")
print("=" * 118)

print(
    "KPI:",
    json.dumps(counts, ensure_ascii=False)
)

print(
    "BLOCK hiệu lực:",
    preview.get("effective_block_count")
)

print(
    "Số operation BLOCK:",
    len(by_op)
)

for n, op_id in enumerate(sorted(by_op), 1):
    print()
    print("-" * 118)
    print(f"{n}. {op_id}")

    for item in by_op[op_id]:
        print("   plan_id          :", item["plan_id"])
        print("   xã/phường        :", item["commune"])
        print("   execution_status :", item["execution_status"])
        print("   action_type      :", item["action_type"])
        print("   match_status     :", item["match_status"])
        print("   batch_state      :", item["batch_state"])

        if item["batch_blockers"]:
            print("   LÝ DO BLOCK:")
            for reason in item["batch_blockers"]:
                print("      -", reason)

        if item["audit_blockers"]:
            print("   KIỂM TRA NGUỒN:")
            for reason in item["audit_blockers"]:
                print("      -", reason)

print()
print("=" * 118)
print("DÒNG QĐ3805 CHƯA XÁC ĐỊNH")
print("=" * 118)

if unresolved:
    for item in unresolved:
        print(
            "STT:",
            item.get("stt"),
            "| Trường:",
            item.get("school"),
            "| Xã:",
            item.get("commune"),
            "| operation:",
            item.get("operation_id"),
        )
else:
    print("Không có.")

print()
print("Missing action operation:", len(missing_ops))
print("Duplicate mapping       :", len(duplicates))

db_after = sha256(DB)

print()
print("DB hash trước :", db_before)
print("DB hash sau   :", db_after)

if db_after != db_before:
    raise RuntimeError(
        "DỪNG: hash phocap.db thay đổi ngoài dự kiến."
    )

print("Database      : KHÔNG THAY ĐỔI")
print("Báo cáo       :", OUT)
print("=" * 118)
