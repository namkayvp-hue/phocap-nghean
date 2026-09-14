# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import json
import py_compile
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(r"C:\PhoCap")
HERE = Path(__file__).resolve().parent
DB = ROOT / "data" / "phocap.db"

SERVICE_DST = ROOT / "app" / "services" / "school_merger_official_registry.py"
REG_DST = ROOT / "data" / "school_merger_registry" / "qd3805_level_lock.json"

SERVICE_SRC = HERE / "school_merger_official_registry.py"
REG_SRC = HERE / "school_merger_level_registry_qd3805_enriched_th.json"

BACKUP_ROOT = ROOT / "backups"

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def fail(msg: str, backups: dict[Path, Path]) -> None:
    for dst, src in backups.items():
        try:
            if src.exists():
                shutil.copy2(src, dst)
        except Exception:
            pass
    print("=" * 116)
    print("DỪNG AN TOÀN - KHÓA TRƯỜNG TIỂU HỌC THEO MÃ QĐ3805")
    print("Mã nguồn/registry đã được khôi phục nếu đã chạm file.")
    print("Lỗi:", msg)
    print("Bộ cài KHÔNG thực hiện sáp nhập và KHÔNG chủ động ghi phocap.db.")
    print("=" * 116)
    raise SystemExit(1)

print("=" * 116)
print("KHÓA ĐỐI CHIẾU TRƯỜNG TIỂU HỌC THEO MÃ QĐ3805")
print("Dự án:", ROOT)
print("Database:", DB)
print("Nguyên tắc: KHÔNG thực hiện sáp nhập; KHÔNG chủ động ghi phocap.db.")
print("=" * 116)

if not ROOT.exists():
    raise SystemExit(r"Không tìm thấy C:\PhoCap")
if not DB.exists():
    raise SystemExit("Không tìm thấy database.")
if not SERVICE_DST.exists() or not REG_DST.exists():
    raise SystemExit("Thiếu service/registry nền cần thiết.")
if not SERVICE_SRC.exists() or not REG_SRC.exists():
    raise SystemExit("Thiếu file đi kèm bộ cài.")

current_service = SERVICE_DST.read_text(encoding="utf-8")
required_markers = [
    "def list_official_registry_plans",
    "def _member_with_db",
    "school_merger_official_registry.json",
]
if not all(x in current_service for x in required_markers):
    raise SystemExit("Service hiện tại không đúng nền chức năng sáp nhập đã khóa.")

db_before = sha256(DB)
stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
backup_dir = BACKUP_ROOT / f"backup_truoc_khoa_ma_qd3805_TH_{stamp}"
backup_dir.mkdir(parents=True, exist_ok=True)

backups = {}
for dst in [SERVICE_DST, REG_DST]:
    backup = backup_dir / dst.name
    shutil.copy2(dst, backup)
    backups[dst] = backup

try:
    shutil.copy2(SERVICE_SRC, SERVICE_DST)
    shutil.copy2(REG_SRC, REG_DST)

    py_compile.compile(str(SERVICE_DST), doraise=True)

    code = r"""
import json
from collections import Counter
from app.services.school_merger_official_registry import list_official_registry_plans
plans = list_official_registry_plans(level_code='TH', display_mode='mapped')
c = Counter(str(x.get('match_status') or '') for x in plans)
code_count = sum(int(x.get('code_matched_school_count') or 0) for x in plans)
print(json.dumps({'plans': len(plans), 'match_status': dict(c), 'code_matched_schools': code_count}, ensure_ascii=False))
"""
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )
    if proc.returncode != 0:
        fail("Smoke audit lỗi:\n" + (proc.stderr or proc.stdout), backups)

    db_after = sha256(DB)
    if db_before != db_after:
        fail("Hash phocap.db thay đổi trong khi bộ cài chỉ được phép đọc.", backups)

    reg = json.loads(REG_DST.read_text(encoding="utf-8"))
    enrich = ((reg.get("enrichments") or {}).get("TH_2025_2026_school_codes") or {})
    remaining_missing_source_codes = enrich.get("remaining_missing_source_codes")
    if remaining_missing_source_codes is None:
        fail("Registry sau cài thiếu chỉ tiêu remaining_missing_source_codes.", backups)
    if int(remaining_missing_source_codes) != 0:
        fail(
            "Registry sau cài vẫn còn thiếu mã nguồn Tiểu học: "
            + str(remaining_missing_source_codes),
            backups,
        )

    recovered_source_codes = enrich.get("recovered_source_codes")
    unresolved_source_codes = enrich.get("unresolved_source_codes")
    if recovered_source_codes is None or int(recovered_source_codes) != 60:
        fail(
            "Số mã nguồn Tiểu học đã khôi phục không đúng 60: "
            + str(recovered_source_codes),
            backups,
        )
    if unresolved_source_codes is None or int(unresolved_source_codes) != 0:
        fail(
            "Registry còn mã nguồn Tiểu học chưa giải quyết: "
            + str(unresolved_source_codes),
            backups,
        )

    print()
    print("=" * 116)
    print("CÀI ĐẶT THÀNH CÔNG - ĐÃ KHÓA TRƯỜNG TIỂU HỌC THEO MÃ QĐ3805")
    print("Đã bổ sung 60 mã trường nguồn còn thiếu từ danh mục mạng lưới 2025-2026.")
    print("Official registry ưu tiên MÃ QĐ3805; tên trường chỉ còn là fallback.")
    print("Trường nguồn khác xã hiện tại vẫn được nhận đúng nếu mã trường là duy nhất.")
    print("Database: KHÔNG THAY ĐỔI")
    print("Smoke audit:", proc.stdout.strip())
    print("Backup:", backup_dir)
    print("Bộ cài KHÔNG thực hiện sáp nhập.")
    print("=" * 116)

except SystemExit:
    raise
except Exception as exc:
    fail(str(exc), backups)
