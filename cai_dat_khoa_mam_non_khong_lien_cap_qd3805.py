# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import json
import py_compile
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(r"C:\PhoCap")
HERE = Path(__file__).resolve().parent

DB = ROOT / "data" / "phocap.db"
SERVICE = ROOT / "app" / "services" / "school_merger_official_registry.py"
NEW_SERVICE = HERE / "school_merger_official_registry.py"
LEVEL_LOCK = ROOT / "data" / "school_merger_registry" / "qd3805_level_lock.json"

EXPECTED_OLD_HASH = "c97675ebb56670914b535932fca876116b61387437e47785b13443c87f890b7a"
EXPECTED_NEW_HASH = "12cb62d3cd9cc7e2834b5658506c8825943a9c8820f0e7b89a7b647e47db4264"

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024*1024), b""):
            h.update(block)
    return h.hexdigest()

def db_check():
    con = sqlite3.connect(DB.resolve().as_uri() + "?mode=ro", uri=True, timeout=30)
    try:
        con.execute("PRAGMA query_only=ON")
        integrity = str(con.execute("PRAGMA integrity_check").fetchone()[0])
        fk = len(con.execute("PRAGMA foreign_key_check").fetchall())
        return integrity, fk
    finally:
        con.close()

def smoke():
    code = r"""
import json
from app.services.school_merger_official_registry import list_official_registry_plans
from app.services.school_merger_level_batch_service import build_level_batch_preview

mn = list_official_registry_plans(school_year_id=2, level_code="MN", display_mode="all")
target = []
violations = []

for p in mn:
    rows = sorted(
        int(x.get("excel_row"))
        for x in (p.get("member_schools") or [])
        if x.get("excel_row") is not None
    )
    op = str(p.get("qd3805_mn_lock_operation_id") or "")
    locked = sorted(int(x) for x in (p.get("qd3805_mn_lock_member_rows") or []))
    if op:
        if rows != locked:
            violations.append({"plan_id": p.get("id"), "op": op, "rows": rows, "locked": locked})
    if 1327 in rows or 1328 in rows or 1329 in rows:
        target.append({
            "plan_id": p.get("id"),
            "op": op,
            "rows": rows,
            "levels": p.get("level_codes"),
            "members": [
                {
                    "excel_row": x.get("excel_row"),
                    "excel_name": x.get("excel_name"),
                    "code": x.get("code"),
                }
                for x in (p.get("member_schools") or [])
            ],
            "target": (p.get("target_school") or {}).get("excel_name") or (p.get("target_school") or {}).get("name"),
        })

pm = build_level_batch_preview(school_year_id=2, level_code="MN")
pth = build_level_batch_preview(school_year_id=2, level_code="TH")

print(json.dumps({
    "mn_plan_0680_like": target,
    "mn_member_lock_violations": violations,
    "mn_counts": pm.get("counts"),
    "mn_effective_block": pm.get("effective_block_count"),
    "mn_excluded": pm.get("excluded_cross_level_count"),
    "mn_expected": pm.get("registry_action_expected_count"),
    "mn_mapped": pm.get("registry_action_mapped_count"),
    "th_counts": pth.get("counts"),
    "th_previous_batch": bool(pth.get("previous_batch")),
}, ensure_ascii=True))
"""
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=240,
        env={
            **__import__("os").environ,
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8": "1",
        },
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr or proc.stdout)
    return json.loads((proc.stdout or "").strip().splitlines()[-1])

print("="*118)
print("KHÓA MẦM NON QĐ3805: KHÔNG CÓ LIÊN CẤP")
print("Dự án:", ROOT)
print("Database:", DB)
print("Bộ cài KHÔNG thực hiện sáp nhập và KHÔNG ghi phocap.db.")
print("="*118)

for p in (DB, SERVICE, NEW_SERVICE, LEVEL_LOCK):
    if not p.exists():
        raise SystemExit("Thiếu file bắt buộc: " + str(p))

current_hash = sha256(SERVICE)
if current_hash != EXPECTED_OLD_HASH:
    raise SystemExit(
        "school_merger_official_registry.py không đúng nền đã khóa. "
        "Hash hiện tại: " + current_hash
    )
if sha256(NEW_SERVICE) != EXPECTED_NEW_HASH:
    raise SystemExit("Service đi kèm ZIP không đúng hash.")

lock = json.loads(LEVEL_LOCK.read_text(encoding="utf-8"))
mn_ops = [
    x for x in (lock.get("operations") or [])
    if str((x or {}).get("batch") or "").upper() == "MN"
]
bad_mn = [
    x for x in mn_ops
    if set(str(v or "").upper() for v in (x.get("source_levels") or [])) - {"MN"}
    or set(str(v or "").upper() for v in (x.get("target_levels") or [])) - {"MN"}
]
if len(mn_ops) != 192:
    raise SystemExit(f"Bảng khóa hiện có {len(mn_ops)} action MN; dự kiến 192.")
if bad_mn:
    raise SystemExit("Bảng khóa QĐ3805 có operation MN chứa cấp khác; dừng, không vá.")

op680 = next((x for x in mn_ops if x.get("operation_id") == "QD3805-OP-0680"), None)
if op680 is None:
    raise SystemExit("Không tìm thấy QD3805-OP-0680.")
rows680 = sorted(int(x.get("excel_row")) for x in (op680.get("source_schools") or []))
if rows680 != [1327,1328,1329]:
    raise SystemExit("OP-0680 không còn đúng 3 dòng MN 1327-1329; dừng.")

integrity, fk = db_check()
if integrity.lower() != "ok" or fk:
    raise SystemExit(f"Database không đạt integrity/FK: {integrity}, fk={fk}")

db_before = sha256(DB)
stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
backup_dir = ROOT / "backups" / f"backup_truoc_khoa_MN_khong_lien_cap_{stamp}"
backup_dir.mkdir(parents=True, exist_ok=False)
backup_service = backup_dir / SERVICE.name
shutil.copy2(SERVICE, backup_service)

try:
    shutil.copy2(NEW_SERVICE, SERVICE)
    py_compile.compile(str(SERVICE), doraise=True)

    result = smoke()

    if result.get("mn_member_lock_violations"):
        raise RuntimeError(
            "Sau cài vẫn có plan MN lệch dòng so với bảng khóa: "
            + json.dumps(result["mn_member_lock_violations"][:5], ensure_ascii=False)
        )

    target = result.get("mn_plan_0680_like") or []
    if len(target) != 1:
        raise RuntimeError(f"Không khóa duy nhất được OP-0680; tìm thấy {len(target)} plan.")
    t = target[0]
    if t.get("rows") != [1327,1328,1329]:
        raise RuntimeError("OP-0680 sau cài không còn đúng 3 dòng MN.")
    if [str(x or "").upper() for x in (t.get("levels") or [])] != ["MN"]:
        raise RuntimeError("OP-0680 sau cài chưa khóa level_codes=['MN'].")
    if any("Tiểu học" in str(x.get("excel_name") or "") for x in (t.get("members") or [])):
        raise RuntimeError("OP-0680 vẫn còn trường Tiểu học trong member_schools.")

    if int(result.get("mn_expected") or 0) != 192 or int(result.get("mn_mapped") or 0) != 192:
        raise RuntimeError("Sau cài MN không còn ghép đủ 192/192.")
    if int(result.get("mn_excluded") or 0) != 0:
        raise RuntimeError("Mầm non vẫn xuất hiện liên cấp/đặc thù sau cài.")

    th_counts = result.get("th_counts") or {}
    if (
        int(th_counts.get("DONE") or 0) != 160
        or int(th_counts.get("READY") or 0) != 0
        or int(th_counts.get("BLOCK") or 0) != 0
        or not bool(result.get("th_previous_batch"))
    ):
        raise RuntimeError(
            "Trạng thái Tiểu học đã đóng bị thay đổi ngoài dự kiến: "
            + json.dumps({"counts": th_counts, "previous_batch": result.get("th_previous_batch")}, ensure_ascii=False)
        )

    if sha256(DB) != db_before:
        raise RuntimeError("Hash phocap.db thay đổi ngoài dự kiến.")

    report_dir = ROOT / "exports" / "Khoa_Mam_Non_Khong_Lien_Cap_QD3805"
    report_dir.mkdir(parents=True, exist_ok=True)
    report = report_dir / f"bao_cao_khoa_MN_khong_lien_cap_{stamp}.json"
    report.write_text(json.dumps({
        "installed_at": datetime.now().isoformat(timespec="seconds"),
        "database_unchanged": True,
        "old_service_hash": EXPECTED_OLD_HASH,
        "new_service_hash": EXPECTED_NEW_HASH,
        "smoke": result,
        "backup_service": str(backup_service),
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print()
    print("="*118)
    print("CÀI ĐẶT THÀNH CÔNG - MẦM NON ĐÃ KHÓA TUYỆT ĐỐI KHÔNG LIÊN CẤP")
    print("QĐ3805 MN action: 192/192")
    print("Liên cấp/đặc thù MN: 0")
    print("OP-0680 Quang Đồng: chỉ còn 3 trường Mầm non, không còn Tiểu học Đồng Thành.")
    print("KPI MN sau sửa:", json.dumps(result.get("mn_counts") or {}, ensure_ascii=False))
    print("BLOCK hiệu lực MN:", result.get("mn_effective_block"))
    print("Tiểu học đã đóng: giữ nguyên 160 DONE / 0 READY / 0 BLOCK.")
    print("Database: KHÔNG THAY ĐỔI")
    print("Bộ cài KHÔNG thực hiện sáp nhập.")
    print("Backup:", backup_dir)
    print("Báo cáo:", report)
    print("="*118)

except Exception as exc:
    try:
        shutil.copy2(backup_service, SERVICE)
    except Exception:
        pass
    print("="*118)
    print("DỪNG AN TOÀN - ĐÃ KHÔI PHỤC SERVICE CŨ")
    print("Lỗi:", exc)
    print("Database: KHÔNG CHỦ ĐỘNG GHI")
    print("="*118)
    raise SystemExit(1)
