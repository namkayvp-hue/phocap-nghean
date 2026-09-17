import json
from pathlib import Path

REPORT = Path(r"C:\PhoCap\exports\chan_doan_181_MN_QD3805.json")

SPECIAL = {
    "QD3805-OP-0141",
    "QD3805-OP-0244",
    "QD3805-OP-0704",
}

MISSING = {
    "QD3805-OP-0410",
    "QD3805-OP-0282",
    "QD3805-OP-0449",
    "QD3805-OP-0592",
    "QD3805-OP-0600",
}

if not REPORT.exists():
    raise SystemExit("Không tìm thấy: " + str(REPORT))

data = json.loads(REPORT.read_text(encoding="utf-8"))

before = data.get("before_preview") or {}
after = data.get("after_preview") or {}

OP_KEYS = (
    "operation_id",
    "op_id",
    "operation",
)

STATUS_KEYS = (
    "status",
    "action_status",
    "state",
    "result",
    "decision",
    "action",
)

def walk(obj, path="root"):
    if isinstance(obj, dict):
        yield path, obj
        for k, v in obj.items():
            yield from walk(v, f"{path}.{k}")

    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from walk(v, f"{path}[{i}]")

def get_op_id(d):
    for k in OP_KEYS:
        v = d.get(k)
        if isinstance(v, str) and v.startswith("QD3805-OP-"):
            return v.strip()
    return None

def scalar_summary(d):
    out = {}
    for k, v in d.items():
        if isinstance(v, (str, int, float, bool)) or v is None:
            out[k] = v
    return out

def collect(root):
    result = {}

    for path, d in walk(root):
        op_id = get_op_id(d)
        if not op_id:
            continue

        result.setdefault(op_id, []).append({
            "path": path,
            "data": scalar_summary(d),
        })

    return result

B = collect(before)
A = collect(after)

print("=" * 120)
print("XÁC ĐỊNH 1 PHƯƠNG ÁN CHUYỂN SANG DONE")
print("CHỈ ĐỌC FILE CHẨN ĐOÁN")
print("=" * 120)

print("\nCOUNTS:")
print("before =", json.dumps(before.get("mn_counts") or before.get("counts") or {}, ensure_ascii=False))
print("after  =", json.dumps(after.get("mn_counts") or after.get("counts") or {}, ensure_ascii=False))

print("\nSố operation tìm thấy:")
print("before =", len(B))
print("after  =", len(A))

# -------------------------------------------------------------
# So sánh mọi operation có mặt ở cả trước và sau
# -------------------------------------------------------------
print("\n" + "=" * 120)
print("CÁC OPERATION CÓ DỮ LIỆU KHÁC GIỮA BEFORE / AFTER")
print("=" * 120)

changed = []

for op_id in sorted(set(B) | set(A)):
    b = B.get(op_id, [])
    a = A.get(op_id, [])

    b_text = json.dumps(b, ensure_ascii=False, sort_keys=True)
    a_text = json.dumps(a, ensure_ascii=False, sort_keys=True)

    if b_text != a_text:
        changed.append(op_id)

        print("\n>>>", op_id)

        print("BEFORE:")
        for item in b:
            print(" path =", item["path"])
            print(" data =", json.dumps(item["data"], ensure_ascii=False))

        print("AFTER:")
        for item in a:
            print(" path =", item["path"])
            print(" data =", json.dumps(item["data"], ensure_ascii=False))

print("\nTổng operation có thay đổi:", len(changed))

# -------------------------------------------------------------
# In riêng 5 mã thiếu
# -------------------------------------------------------------
print("\n" + "=" * 120)
print("5 PHƯƠNG ÁN VỪA KHÓA MÃ")
print("=" * 120)

for op_id in sorted(MISSING):
    print("\n###", op_id)

    print("BEFORE:")
    if not B.get(op_id):
        print("  <không có record>")
    for item in B.get(op_id, []):
        print(" ", item["path"])
        print(" ", json.dumps(item["data"], ensure_ascii=False))

    print("AFTER:")
    if not A.get(op_id):
        print("  <không có record>")
    for item in A.get(op_id, []):
        print(" ", item["path"])
        print(" ", json.dumps(item["data"], ensure_ascii=False))

# -------------------------------------------------------------
# In riêng 3 đặc thù
# -------------------------------------------------------------
print("\n" + "=" * 120)
print("3 ĐẶC THÙ CÙNG CẤP")
print("=" * 120)

for op_id in sorted(SPECIAL):
    print("\n###", op_id)

    for item in A.get(op_id, []):
        print(" ", item["path"])
        print(" ", json.dumps(item["data"], ensure_ascii=False))

# -------------------------------------------------------------
# Tìm mọi record AFTER có giá trị DONE
# -------------------------------------------------------------
print("\n" + "=" * 120)
print("RECORD AFTER CÓ TRẠNG THÁI DONE")
print("=" * 120)

done_ids = set()

for op_id, items in A.items():
    for item in items:
        d = item["data"]

        values = [
            str(d.get(k) or "").strip().upper()
            for k in STATUS_KEYS
            if k in d
        ]

        if "DONE" in values:
            done_ids.add(op_id)

print("Số operation nhận diện DONE =", len(done_ids))

for op_id in sorted(done_ids):
    marker = ""

    if op_id in MISSING:
        marker += "  <<< 5 MÃ THIẾU"

    if op_id in SPECIAL:
        marker += "  <<< ĐẶC THÙ"

    print(op_id + marker)

OUT = Path(r"C:\PhoCap\exports\xac_dinh_1_DONE_them_MN_QD3805.json")

OUT.write_text(
    json.dumps({
        "changed_operation_ids": changed,
        "missing_operations": {
            x: {
                "before": B.get(x, []),
                "after": A.get(x, []),
            }
            for x in sorted(MISSING)
        },
        "special_operations": {
            x: A.get(x, [])
            for x in sorted(SPECIAL)
        },
        "done_operation_ids_after": sorted(done_ids),
    }, ensure_ascii=False, indent=2),
    encoding="utf-8",
)

print("\n" + "=" * 120)
print("REPORT:", OUT)
print("KHÔNG SỬA DATABASE.")
print("KHÔNG SỬA FILE CÀI.")
print("=" * 120)
