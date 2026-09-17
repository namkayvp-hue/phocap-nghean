import json
from pathlib import Path
from collections import defaultdict

REPORT = Path(r"C:\PhoCap\exports\chan_doan_181_MN_QD3805.json")

FOCUS = {
    "QD3805-OP-0282",
    "QD3805-OP-0410",
    "QD3805-OP-0449",
    "QD3805-OP-0592",
    "QD3805-OP-0600",
}

if not REPORT.exists():
    raise SystemExit("Không tìm thấy: " + str(REPORT))

data = json.loads(REPORT.read_text(encoding="utf-8"))

before = data.get("before_preview") or {}
after = data.get("after_preview") or {}

def aggregate(preview):
    grouped = defaultdict(list)

    for row in preview.get("rows") or []:
        if not isinstance(row, dict):
            continue

        op_id = str(row.get("qd3805_operation_id") or "").strip()
        if not op_id:
            continue

        grouped[op_id].append(row)

    result = {}

    for op_id, rows in grouped.items():
        states = {
            str(r.get("batch_state") or "BLOCK").upper().strip()
            for r in rows
        }

        # Theo đúng nguyên tắc service:
        # nếu cùng operation xuất hiện nhiều trạng thái khác nhau
        # thì coi là BLOCK.
        state = next(iter(states)) if len(states) == 1 else "BLOCK"

        result[op_id] = {
            "state": state,
            "states": sorted(states),
            "rows": rows,
        }

    return result

B = aggregate(before)
A = aggregate(after)

print("=" * 120)
print("SO SÁNH OPERATION BEFORE / AFTER")
print("CHỈ ĐỌC JSON - KHÔNG CHẠM DATABASE - KHÔNG CHẠM FILE CÀI")
print("=" * 120)

print("\nCOUNTS")
print("before =", json.dumps(before.get("counts") or {}, ensure_ascii=False))
print("after  =", json.dumps(after.get("counts") or {}, ensure_ascii=False))

print("\n" + "=" * 120)
print("TẤT CẢ OPERATION CÓ CHUYỂN TRẠNG THÁI")
print("=" * 120)

changed = []

for op_id in sorted(set(B) | set(A)):
    b = B.get(op_id, {}).get("state", "<KHÔNG CÓ>")
    a = A.get(op_id, {}).get("state", "<KHÔNG CÓ>")

    if b != a:
        changed.append((op_id, b, a))
        print(f"{op_id}: {b}  -->  {a}")

print("\nTổng operation đổi trạng thái:", len(changed))

print("\n" + "=" * 120)
print("RIÊNG 5 PHƯƠNG ÁN VỪA KHÓA MÃ")
print("=" * 120)

for op_id in sorted(FOCUS):
    b = B.get(op_id)
    a = A.get(op_id)

    print("\n###", op_id)
    print("BEFORE STATE =", b["state"] if b else "<KHÔNG CÓ>")
    print("AFTER  STATE =", a["state"] if a else "<KHÔNG CÓ>")

    for label, obj in (("BEFORE", b), ("AFTER", a)):
        if not obj:
            continue

        for i, row in enumerate(obj["rows"], 1):
            print(f"\n  {label} ROW {i}")
            print("  plan_id          =", row.get("id"))
            print("  operation_id     =", row.get("qd3805_operation_id"))
            print("  batch_state      =", row.get("batch_state"))
            print("  batch_label      =", row.get("batch_label"))
            print("  execution_status =", row.get("execution_status"))
            print("  action_type      =", row.get("action_type"))
            print("  match_status     =", row.get("match_status"))

            pc = row.get("qd3805_precompleted")
            if pc is not None:
                print(
                    "  precompleted     =",
                    json.dumps(pc, ensure_ascii=False, default=str)
                )

            blockers = row.get("batch_blockers") or []
            if blockers:
                print(
                    "  blockers         =",
                    json.dumps(blockers, ensure_ascii=False)
                )

print("\n" + "=" * 120)
print("OPERATION TRONG 5 MÃ ĐANG DONE SAU KHÓA")
print("=" * 120)

focus_done = []

for op_id in sorted(FOCUS):
    if A.get(op_id, {}).get("state") == "DONE":
        focus_done.append(op_id)
        print(op_id)

print("\nSố lượng =", len(focus_done))

print("\n" + "=" * 120)
print("KẾT LUẬN TỰ ĐỘNG")
print("=" * 120)

block_to_done = [
    (op, b, a)
    for op, b, a in changed
    if a == "DONE" and b != "DONE"
]

if len(block_to_done) == 1:
    print(
        "ĐÃ XÁC ĐỊNH DUY NHẤT:",
        block_to_done[0][0],
        block_to_done[0][1],
        "->",
        block_to_done[0][2],
    )
else:
    print(
        "Số operation mới chuyển sang DONE:",
        len(block_to_done)
    )
    for x in block_to_done:
        print(x)

print("=" * 120)
