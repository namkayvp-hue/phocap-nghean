from pathlib import Path
from datetime import datetime
import shutil

FILE = Path(
    r"C:\PhoCap\cai_dat_MN_QD3805_tach_3_dac_thu_va_khoa_ma_an_toan.py"
)

text = FILE.read_text(encoding="utf-8")

old = '''    if int(counts.get("DONE") or 0) != 181:
        raise RuntimeError("181 phương án đã hoàn tất trước không được thay đổi.")
    if int(counts.get("READY") or 0) + int(counts.get("BLOCK") or 0) != 8:
        raise RuntimeError(
            "Sau khi tách 3 đặc thù phải còn đúng 8 action toàn trường chưa hoàn tất: "
            + json.dumps(counts, ensure_ascii=False)
        )
'''

new = r'''    # ============================================================
    # KHÓA AN TOÀN MN SAU KHI BỔ SUNG 5 MÃ
    #
    # Nền cũ:
    #   DONE=181, BLOCK=11
    #
    # Sau khi tách đúng 3 đặc thù:
    #   còn 8 operation thuần chưa hoàn tất.
    #
    # Sau khi khóa đủ 5 mã:
    #   OP-0282 được nhận diện lại đúng là COMPLETED_LEGACY,
    #   tức đã thực hiện từ trước, KHÔNG phải thực hiện mới.
    #
    # Trạng thái đúng phải là:
    #   KEEP=51, DONE=182, READY=0, BLOCK=7
    #
    # Không chỉ kiểm số tổng: phải xác minh đích danh OP-0282.
    # ============================================================

    if (
        int(counts.get("KEEP") or 0) != 51
        or int(counts.get("DONE") or 0) != 182
        or int(counts.get("READY") or 0) != 0
        or int(counts.get("BLOCK") or 0) != 7
    ):
        raise RuntimeError(
            "KPI MN sau khóa 5 mã không đúng trạng thái đã kiểm chứng: "
            + json.dumps(counts, ensure_ascii=False)
        )

    import subprocess as _subprocess
    import sys as _sys

    _verify_code = r"""
import json
import sqlite3
from pathlib import Path

from app.services.school_merger_level_batch_service import (
    build_level_batch_preview,
)

FOCUS = {
    "QD3805-OP-0282",
    "QD3805-OP-0410",
    "QD3805-OP-0449",
    "QD3805-OP-0592",
    "QD3805-OP-0600",
}

db = Path("data/phocap.db")

con = sqlite3.connect(
    db.resolve().as_uri() + "?mode=ro",
    uri=True,
)
con.execute("PRAGMA query_only=ON")

year = con.execute(
    """
    SELECT id
    FROM school_years
    WHERE REPLACE(
        REPLACE(code,'–','-'),
        '—','-'
    )='2026-2027'
    LIMIT 1
    """
).fetchone()

con.close()

if year is None:
    raise RuntimeError(
        "Không tìm thấy năm học 2026-2027."
    )

preview = build_level_batch_preview(
    school_year_id=int(year[0]),
    level_code="MN",
)

focus = {}

for raw in preview.get("rows") or []:
    if not isinstance(raw, dict):
        continue

    op_id = str(
        raw.get("qd3805_operation_id") or ""
    ).strip()

    if op_id not in FOCUS:
        continue

    focus.setdefault(op_id, []).append({
        "plan_id": raw.get("id"),
        "batch_state": raw.get("batch_state"),
        "batch_label": raw.get("batch_label"),
        "execution_status": raw.get(
            "execution_status"
        ),
    })

payload = {
    "counts": preview.get("counts") or {},
    "focus": focus,
}

print(
    json.dumps(
        payload,
        ensure_ascii=True,
        default=str,
    )
)
"""

    _proc = _subprocess.run(
        [_sys.executable, "-c", _verify_code],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if _proc.returncode != 0:
        raise RuntimeError(
            "Không kiểm chứng được trạng thái 5 mã:\n"
            + (_proc.stderr or _proc.stdout or "")
        )

    try:
        _verify = json.loads(
            (_proc.stdout or "").strip()
        )
    except Exception as _exc:
        raise RuntimeError(
            "Kết quả kiểm chứng 5 mã không phải JSON hợp lệ."
        ) from _exc

    _raw_counts = _verify.get("counts") or {}
    _focus = _verify.get("focus") or {}

    # Raw preview cũng phải đúng tuyệt đối 182/0/7.
    if (
        int(_raw_counts.get("KEEP") or 0) != 51
        or int(_raw_counts.get("DONE") or 0) != 182
        or int(_raw_counts.get("READY") or 0) != 0
        or int(_raw_counts.get("BLOCK") or 0) != 7
    ):
        raise RuntimeError(
            "RAW preview MN không đúng KPI đã kiểm chứng: "
            + json.dumps(
                _raw_counts,
                ensure_ascii=False,
            )
        )

    _expected_ids = {
        "QD3805-OP-0282",
        "QD3805-OP-0410",
        "QD3805-OP-0449",
        "QD3805-OP-0592",
        "QD3805-OP-0600",
    }

    if set(_focus) != _expected_ids:
        raise RuntimeError(
            "Không thu được đúng 5 operation cần kiểm chứng: "
            + json.dumps(
                _focus,
                ensure_ascii=False,
            )
        )

    # Mỗi operation phải ghép đúng một plan.
    for _op_id in sorted(_expected_ids):
        _items = _focus.get(_op_id) or []

        if len(_items) != 1:
            raise RuntimeError(
                f"{_op_id}: phải ghép đúng 1 plan, "
                f"nhưng có {len(_items)}."
            )

    # OP-0282 là operation DUY NHẤT được tăng thêm vào DONE,
    # và bắt buộc phải do dấu vết COMPLETED_LEGACY.
    _op0282 = _focus["QD3805-OP-0282"][0]

    if (
        str(
            _op0282.get("batch_state") or ""
        ).upper() != "DONE"
        or str(
            _op0282.get("execution_status") or ""
        ).upper() != "COMPLETED_LEGACY"
    ):
        raise RuntimeError(
            "OP-0282 không đúng dấu vết "
            "DONE / COMPLETED_LEGACY: "
            + json.dumps(
                _op0282,
                ensure_ascii=False,
            )
        )

    # Bốn operation còn lại tuyệt đối chưa được chuyển thành DONE.
    for _op_id in (
        "QD3805-OP-0410",
        "QD3805-OP-0449",
        "QD3805-OP-0592",
        "QD3805-OP-0600",
    ):
        _item = _focus[_op_id][0]

        if str(
            _item.get("batch_state") or ""
        ).upper() != "BLOCK":
            raise RuntimeError(
                f"{_op_id}: phải tiếp tục BLOCK, "
                "không được tự chuyển trạng thái: "
                + json.dumps(
                    _item,
                    ensure_ascii=False,
                )
            )

    print(
        "ĐÃ XÁC MINH: 181 DONE cũ + "
        "OP-0282 COMPLETED_LEGACY = 182 DONE."
    )
    print(
        "4 operation còn lại trong 5 mã vẫn BLOCK."
    )
'''

if old not in text:
    raise RuntimeError(
        "Không tìm thấy đúng khối khóa 181/8 cần thay. "
        "DỪNG AN TOÀN - FILE CHƯA THAY ĐỔI."
    )

backup = FILE.with_name(
    FILE.stem
    + "_backup_truoc_khoa_182_OP0282_"
    + datetime.now().strftime("%Y%m%d_%H%M%S")
    + FILE.suffix
)

shutil.copy2(FILE, backup)

text = text.replace(old, new, 1)

FILE.write_text(
    text,
    encoding="utf-8",
)

print("=" * 118)
print("ĐÃ NÂNG KHÓA AN TOÀN MN THEO KẾT QUẢ KIỂM CHỨNG")
print("File   :", FILE)
print("Backup :", backup)
print("=" * 118)
print("KHÔNG đổi mù 181 -> 182.")
print("Bắt buộc OP-0282 = DONE / COMPLETED_LEGACY.")
print("Bắt buộc 4 mã còn lại = BLOCK.")
print("KHÔNG thực hiện sáp nhập.")
print("KHÔNG sửa Excel nguồn.")
print("KHÔNG ghi phocap.db.")
print("=" * 118)
