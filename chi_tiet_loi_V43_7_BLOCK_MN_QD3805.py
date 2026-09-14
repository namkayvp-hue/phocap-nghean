import sys
import json
import hashlib
import sqlite3
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(r"C:\PhoCap")
DB = ROOT / "data" / "phocap.db"

OUT = (
    ROOT
    / "exports"
    / "chi_tiet_loi_V43_7_BLOCK_MN_QD3805.json"
)

TARGET_PLANS = {
    "PA2026-785CDDA8D8CC": "QD3805-OP-0175",
    "PA2026-E494BD00A794": "QD3805-OP-0337",
    "PA2026-63A88A615526": "QD3805-OP-0338",
    "PA2026-43804C58D423": "QD3805-OP-0410",
    "PA2026-4AB75BCD93EB": "QD3805-OP-0449",
    "PA2026-7802B1BD1912": "QD3805-OP-0592",
    "PA2026-1E90C6AAFD47": "QD3805-OP-0600",
}

MAPPED_OPS = {
    "QD3805-OP-0175",
    "QD3805-OP-0337",
    "QD3805-OP-0410",
    "QD3805-OP-0449",
    "QD3805-OP-0592",
    "QD3805-OP-0600",
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


def false_paths(obj, path="audit"):
    """
    Thu toàn bộ đường dẫn có giá trị False.
    Không suy đoán tên check.
    """
    out = []

    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{path}.{k}"

            if v is False:
                out.append(p)

            elif isinstance(v, (dict, list)):
                out.extend(false_paths(v, p))

    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            p = f"{path}[{i}]"

            if v is False:
                out.append(p)

            elif isinstance(v, (dict, list)):
                out.extend(false_paths(v, p))

    return out


def interesting_failures(obj, path="audit"):
    """
    Thu thêm các chuỗi giải thích lỗi/block/fail.
    """
    out = []

    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{path}.{k}"

            if isinstance(v, str):
                t = v.lower()

                if any(
                    x in t
                    for x in (
                        "không đạt",
                        "không đúng",
                        "không khớp",
                        "thiếu",
                        "block",
                        "fail",
                        "lỗi",
                    )
                ):
                    out.append((p, v))

            elif isinstance(v, (dict, list)):
                out.extend(
                    interesting_failures(v, p)
                )

    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            p = f"{path}[{i}]"

            if isinstance(v, str):
                t = v.lower()

                if any(
                    x in t
                    for x in (
                        "không đạt",
                        "không đúng",
                        "không khớp",
                        "thiếu",
                        "block",
                        "fail",
                        "lỗi",
                    )
                ):
                    out.append((p, v))

            elif isinstance(v, (dict, list)):
                out.extend(
                    interesting_failures(v, p)
                )

    return out


db_before = sha256(DB)

# ---------------------------------------------------------
# Lấy đúng school_year_id 2026-2027 bằng DB READ ONLY
# ---------------------------------------------------------
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
    raise SystemExit(
        "Không tìm thấy năm học 2026-2027."
    )

from app.services.school_merger_source_audit_service import (
    audit_official_plans,
)

audit_result = audit_official_plans(
    school_year_id=int(year["id"]),
    commune_id=None,
    level_code="MN",
)

selected = []

for raw in audit_result.get("rows") or []:
    if not isinstance(raw, dict):
        continue

    plan = dict(raw.get("plan") or {})
    audit = dict(raw.get("audit") or {})

    pid = str(plan.get("id") or "")

    if pid not in TARGET_PLANS:
        continue

    op_id = TARGET_PLANS[pid]

    selected.append({
        "operation_id": op_id,
        "plan_id": pid,
        "plan": plan,
        "audit": audit,
        "false_paths": false_paths(audit),
        "interesting_failures": [
            {
                "path": p,
                "value": v,
            }
            for p, v
            in interesting_failures(audit)
        ],
    })

OUT.parent.mkdir(
    parents=True,
    exist_ok=True,
)

OUT.write_text(
    json.dumps(
        {
            "school_year_id": int(year["id"]),
            "school_year_code": str(year["code"]),
            "selected": selected,
        },
        ensure_ascii=False,
        indent=2,
        default=str,
    ),
    encoding="utf-8",
)

print("=" * 118)
print("CHI TIẾT CHECK V4.3 - 7 BLOCK MN QĐ3805")
print("CHỈ ĐỌC - KHÔNG SÁP NHẬP - KHÔNG SỬA DB")
print("=" * 118)

print("Số plan tìm thấy:", len(selected))

for item in sorted(
    selected,
    key=lambda x: x["operation_id"],
):
    op_id = item["operation_id"]
    plan = item["plan"]
    audit = item["audit"]

    print()
    print("-" * 118)
    print(
        op_id,
        "|",
        item["plan_id"],
    )

    print(
        "Xã/phường:",
        plan.get("commune_excel")
        or plan.get("commune")
        or "",
    )

    print(
        "action_type:",
        plan.get("action_type"),
    )

    print(
        "audit pass:",
        audit.get("pass"),
    )

    blockers = audit.get("blockers") or []

    if blockers:
        print("BLOCKERS:")

        for x in blockers:
            print("  -", x)

    print()
    print("CÁC CHECK BOOLEAN = FALSE:")

    fp = item["false_paths"]

    if not fp:
        print("  <không tìm thấy boolean False>")
    else:
        for x in fp:
            print("  -", x)

    failures = item["interesting_failures"]

    if failures:
        print()
        print("CÁC DÒNG GIẢI THÍCH LỖI:")

        for x in failures:
            print(
                "  -",
                x["path"],
                "=",
                x["value"],
            )

    # Với 6 operation MAPPED, in sâu các khối
    # có vẻ liên quan trực tiếp tới trường nguồn.
    if op_id in MAPPED_OPS:
        print()
        print("CẤU TRÚC AUDIT ĐẦY ĐỦ:")

        print(
            json.dumps(
                audit,
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        )

    else:
        print()
        print(
            "OP-0338 là SPECIAL/BLOCKED - "
            "GIỮ RIÊNG, chưa tự sửa."
        )

db_after = sha256(DB)

print()
print("=" * 118)
print("KIỂM TRA AN TOÀN")
print("=" * 118)

print("DB hash trước:", db_before)
print("DB hash sau  :", db_after)

if db_before != db_after:
    raise RuntimeError(
        "DỪNG: phocap.db thay đổi ngoài dự kiến."
    )

print("Database     : KHÔNG THAY ĐỔI")
print("Báo cáo      :", OUT)
print("=" * 118)
