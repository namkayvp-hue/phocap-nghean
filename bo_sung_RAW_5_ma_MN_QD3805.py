from pathlib import Path
from datetime import datetime
import shutil

FILE = Path(r"C:\PhoCap\chan_doan_181_MN_QD3805.py")

if not FILE.exists():
    raise SystemExit("Không tìm thấy: " + str(FILE))

text = FILE.read_text(encoding="utf-8")

MARKER = "# RAW_FOCUS_5_MA_MN_QD3805"

if MARKER in text:
    print("Khối RAW đã có sẵn - không chèn lần hai.")
    raise SystemExit(0)

anchor = '''    if int(counts.get("DONE") or 0) != 181:
'''

if anchor not in text:
    raise RuntimeError(
        "Không tìm thấy khóa DONE=181. "
        "Dừng an toàn, không sửa file."
    )

backup = FILE.with_name(
    FILE.stem
    + "_backup_truoc_raw_"
    + datetime.now().strftime("%Y%m%d_%H%M%S")
    + FILE.suffix
)
shutil.copy2(FILE, backup)

insert = r'''
    # RAW_FOCUS_5_MA_MN_QD3805
    # ------------------------------------------------------------
    # Chạy subprocess riêng để chắc chắn import SERVICE MỚI
    # đang được đặt tạm thời trong lần chẩn đoán này.
    # Chỉ đọc preview; KHÔNG gọi hàm thực hiện sáp nhập.
    # ------------------------------------------------------------
    import subprocess as _subprocess
    import sys as _sys

    _probe_code = r"""
import json

from app.services.school_merger_level_batch_service import build_level_batch_preview

FOCUS = {
    "QD3805-OP-0282",
    "QD3805-OP-0410",
    "QD3805-OP-0449",
    "QD3805-OP-0592",
    "QD3805-OP-0600",
}

preview = build_level_batch_preview(
    school_year_id=2,
    level_code="MN",
)

focus_rows = []

for raw in preview.get("rows") or []:
    if not isinstance(raw, dict):
        continue

    op_id = str(raw.get("qd3805_operation_id") or "").strip()

    if op_id not in FOCUS:
        continue

    audit = raw.get("source_audit") or {}

    focus_rows.append({
        "plan_id": raw.get("id"),
        "operation_id": op_id,
        "batch_state": raw.get("batch_state"),
        "batch_label": raw.get("batch_label"),
        "execution_status": raw.get("execution_status"),
        "action_type": raw.get("action_type"),
        "match_status": raw.get("match_status"),
        "commune": raw.get("commune_excel"),
        "qd3805_precompleted": raw.get("qd3805_precompleted"),
        "source_audit_pass": audit.get("pass"),
        "source_audit_blockers": audit.get("blockers"),
        "batch_blockers": raw.get("batch_blockers"),
    })

payload = {
    "counts": preview.get("counts") or {},
    "focus_rows": focus_rows,
}

print(json.dumps(
    payload,
    ensure_ascii=False,
    default=str
))
"""

    _proc = _subprocess.run(
        [_sys.executable, "-c", _probe_code],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if _proc.returncode != 0:
        raise RuntimeError(
            "Không lấy được RAW preview:\n"
            + (_proc.stderr or _proc.stdout or "")
        )

    _raw_text = (_proc.stdout or "").strip()

    try:
        _raw_payload = json.loads(_raw_text)
    except Exception as _exc:
        raise RuntimeError(
            "RAW preview không trả JSON hợp lệ:\n"
            + _raw_text
        ) from _exc

    _raw_report = (
        ROOT
        / "exports"
        / "RAW_5_MA_MN_QD3805_SAU_KHOA.json"
    )

    _raw_report.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    _raw_report.write_text(
        json.dumps(
            _raw_payload,
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )

    print()
    print("=" * 118)
    print("RAW 5 PHƯƠNG ÁN SAU KHI KHÓA MÃ")
    print("=" * 118)

    print(
        "counts =",
        json.dumps(
            _raw_payload.get("counts") or {},
            ensure_ascii=False,
        ),
    )

    _focus_rows = (
        _raw_payload.get("focus_rows") or []
    )

    for _row in _focus_rows:
        print()
        print(
            "OPERATION:",
            _row.get("operation_id"),
        )
        print(
            "  plan_id          =",
            _row.get("plan_id"),
        )
        print(
            "  batch_state      =",
            _row.get("batch_state"),
        )
        print(
            "  batch_label      =",
            _row.get("batch_label"),
        )
        print(
            "  execution_status =",
            _row.get("execution_status"),
        )
        print(
            "  action_type      =",
            _row.get("action_type"),
        )
        print(
            "  match_status     =",
            _row.get("match_status"),
        )
        print(
            "  commune          =",
            _row.get("commune"),
        )

        if _row.get("qd3805_precompleted") is not None:
            print(
                "  PRECOMPLETED     =",
                json.dumps(
                    _row.get("qd3805_precompleted"),
                    ensure_ascii=False,
                    default=str,
                ),
            )

        print(
            "  audit_pass       =",
            _row.get("source_audit_pass"),
        )

        if _row.get("source_audit_blockers"):
            print(
                "  audit_blockers   =",
                json.dumps(
                    _row.get("source_audit_blockers"),
                    ensure_ascii=False,
                ),
            )

        if _row.get("batch_blockers"):
            print(
                "  batch_blockers   =",
                json.dumps(
                    _row.get("batch_blockers"),
                    ensure_ascii=False,
                ),
            )

    _done_focus = [
        x
        for x in _focus_rows
        if str(x.get("batch_state") or "").upper()
        == "DONE"
    ]

    print()
    print("-" * 118)
    print(
        "SỐ PHƯƠNG ÁN TRONG 5 MÃ ĐANG DONE:",
        len(_done_focus),
    )

    for _x in _done_focus:
        print(
            "  >>>",
            _x.get("operation_id"),
            "|",
            _x.get("batch_label"),
        )

    print("RAW REPORT:", _raw_report)
    print("=" * 118)

'''

text = text.replace(
    anchor,
    insert + anchor,
    1,
)

FILE.write_text(
    text,
    encoding="utf-8",
)

print("=" * 110)
print("ĐÃ BỔ SUNG RAW CHẨN ĐOÁN VÀO BẢN RIÊNG")
print("File   :", FILE)
print("Backup :", backup)
print("FILE CÀI CHÍNH: KHÔNG SỬA")
print("DATABASE: KHÔNG GHI")
print("=" * 110)
