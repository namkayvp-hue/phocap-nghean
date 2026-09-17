# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import json
import os
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
BATCH_SERVICE = ROOT / "app" / "services" / "school_merger_level_batch_service.py"
REGISTRY_SERVICE = ROOT / "app" / "services" / "school_merger_official_registry.py"
TEMPLATE = ROOT / "app" / "templates" / "data_tools" / "school_merger_level_batch.html"
LOCK = ROOT / "data" / "school_merger_registry" / "qd3805_level_lock.json"
MN_RESOLUTION = ROOT / "data" / "school_merger_registry" / "qd3805_mn_resolution.json"

NEW_BATCH_SERVICE = HERE / "school_merger_level_batch_service.py"
NEW_TEMPLATE = HERE / "school_merger_level_batch.html"
NEW_RESOLUTION = HERE / "qd3805_mn_resolution.json"

EXPECTED_BATCH_HASH = "ea5b86cf02395d960f53011352bc7dd4450c556710383c912b473dd21c7d5cf2"
EXPECTED_TEMPLATE_HASH = "90c32aa3e27b487c06e65d25d162fe1eb9d85ec05a234528f5303a6c4d7d8012"
EXPECTED_REGISTRY_SERVICE_HASH = "12cb62d3cd9cc7e2834b5658506c8825943a9c8820f0e7b89a7b647e47db4264"
EXPECTED_LOCK_HASH = "26b4356ffd9098ac682b1ed74432c443022fcecbe68724336b2adbfd5f053f98"
EXPECTED_NEW_BATCH_HASH = "79f8f146401af4e8db422e584bbe67cb395cd0d9414c263bd00b1440b216e26f"
EXPECTED_NEW_TEMPLATE_HASH = "d0b85371bc9157a19d1d6d3266c32b572ac454876fce0c55f19a29540ab14721"

CODE_PATCHES = {
    "QD3805-OP-0410": {
        802: "40415304",
        "target_code": "40415304",
        "expected_name_contains": "Tiền Phong",
    },
    "QD3805-OP-0282": {
        537: "40417301",
        "target_code": "40417301",
        "expected_name_contains": "Mường Xén",
    },
    "QD3805-OP-0449": {
        880: "40420313",
        "target_code": "40420322",
        "expected_name_contains": "Châu Thái",
    },
    "QD3805-OP-0592": {
        1148: "40428306",
        "target_code": "40428305",
        "expected_name_contains": "Thanh Đức",
    },
    "QD3805-OP-0600": {
        1169: "40428320",
        "target_code": "40428319",
        "expected_name_contains": "Thanh Hà",
    },
}

SPECIAL_IDS = {
    "QD3805-OP-0141",
    "QD3805-OP-0244",
    "QD3805-OP-0704",
}

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024*1024), b""):
            h.update(block)
    return h.hexdigest()

def atomic_write(path: Path, data: bytes) -> None:
    tmp = path.with_name(path.name + ".mn2.tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)

def db_check():
    con = sqlite3.connect(DB.resolve().as_uri() + "?mode=ro", uri=True, timeout=30)
    try:
        con.execute("PRAGMA query_only=ON")
        integrity = str(con.execute("PRAGMA integrity_check").fetchone()[0])
        fk = len(con.execute("PRAGMA foreign_key_check").fetchall())
        mn_batch = 0
        th_batch = 0
        exists = con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' "
            "AND name='school_merger_level_batches'"
        ).fetchone()
        if exists:
            mn_batch = int(con.execute(
                "SELECT COUNT(*) FROM school_merger_level_batches "
                "WHERE school_year_id=2 AND level_code='MN'"
            ).fetchone()[0])
            th_batch = int(con.execute(
                "SELECT COUNT(*) FROM school_merger_level_batches "
                "WHERE school_year_id=2 AND level_code='TH'"
            ).fetchone()[0])
        return integrity, fk, mn_batch, th_batch
    finally:
        con.close()

def patch_lock(data: dict) -> dict:
    operations = data.get("operations") or []
    index = {
        str(x.get("operation_id") or ""): x
        for x in operations
        if isinstance(x, dict)
    }

    for op_id, patch in CODE_PATCHES.items():
        op = index.get(op_id)
        if op is None:
            raise RuntimeError("Không tìm thấy " + op_id)

        row_patches = {
            int(k): str(v)
            for k, v in patch.items()
            if isinstance(k, int)
        }
        hit_rows = set()
        for src in op.get("source_schools") or []:
            if not isinstance(src, dict):
                continue
            try:
                row = int(src.get("excel_row"))
            except Exception:
                continue
            if row not in row_patches:
                continue

            expected_piece = str(patch.get("expected_name_contains") or "")
            if expected_piece and expected_piece.lower() not in str(src.get("name") or "").lower():
                raise RuntimeError(
                    f"{op_id} row {row} không đúng tên dự kiến: {src.get('name')}"
                )

            code = row_patches[row]
            current = [
                str(x or "").strip()
                for x in (src.get("codes") or [])
                if str(x or "").strip()
            ]
            if current and code not in current:
                raise RuntimeError(
                    f"{op_id} row {row} đã có mã khác: {current}; không tự ghi đè."
                )
            src["codes"] = [code]
            hit_rows.add(row)

        if hit_rows != set(row_patches):
            raise RuntimeError(
                f"{op_id} không tìm đủ row cần khóa. "
                f"Cần={sorted(row_patches)}; thấy={sorted(hit_rows)}"
            )

        all_codes = []
        for src in op.get("source_schools") or []:
            for code in src.get("codes") or []:
                code = str(code or "").strip()
                if code and code not in all_codes:
                    all_codes.append(code)
        op["source_codes"] = all_codes

        target_code = str(patch.get("target_code") or "").strip()
        if target_code:
            current_target = [
                str(x or "").strip()
                for x in (op.get("target_codes") or [])
                if str(x or "").strip()
            ]
            if current_target and target_code not in current_target:
                raise RuntimeError(
                    f"{op_id} target_codes đang khác: {current_target}"
                )
            op["target_codes"] = [target_code]

    return data

def smoke():
    code = r"""
import json
from app.services.school_merger_level_batch_service import build_level_batch_preview

mn = build_level_batch_preview(school_year_id=2, level_code="MN")
th = build_level_batch_preview(school_year_id=2, level_code="TH")

print(json.dumps({
    "mn_counts": mn.get("counts"),
    "mn_expected": mn.get("registry_action_expected_count"),
    "mn_mapped": mn.get("registry_action_mapped_count"),
    "mn_keep": mn.get("registry_keep_expected_count"),
    "mn_cross": mn.get("excluded_cross_level_count"),
    "mn_same_special": mn.get("excluded_same_level_special_count"),
    "mn_same_special_ids": sorted(
        str(x.get("operation_id") or "")
        for x in (mn.get("excluded_same_level_special") or [])
    ),
    "mn_unresolved": mn.get("registry_unresolved_count"),
    "mn_effective_block": mn.get("effective_block_count"),
    "mn_candidate": mn.get("candidate_count"),
    "th_counts": th.get("counts"),
    "th_previous_batch": bool(th.get("previous_batch")),
}, ensure_ascii=True))
"""
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    p = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
        env=env,
    )
    if p.returncode != 0:
        raise RuntimeError(p.stderr or p.stdout)
    return json.loads((p.stdout or "").strip().splitlines()[-1])

print("="*118)
print("MẦM NON QĐ3805 - TÁCH 3 ĐẶC THÙ CÙNG CẤP + KHÓA MÃ 5 TRƯỜNG")
print("Database:", DB)
print("KHÔNG thực hiện sáp nhập. KHÔNG sửa Excel nguồn.")
print("="*118)

for p in (DB, BATCH_SERVICE, REGISTRY_SERVICE, TEMPLATE, LOCK,
          NEW_BATCH_SERVICE, NEW_TEMPLATE, NEW_RESOLUTION):
    if not p.exists():
        raise SystemExit("Thiếu file bắt buộc: " + str(p))

if sha256(BATCH_SERVICE) != EXPECTED_BATCH_HASH:
    raise SystemExit("Batch service không đúng nền đã khóa: " + sha256(BATCH_SERVICE))
if sha256(REGISTRY_SERVICE) != EXPECTED_REGISTRY_SERVICE_HASH:
    raise SystemExit(
        "Official registry service chưa đúng bản Mầm non không liên cấp: "
        + sha256(REGISTRY_SERVICE)
    )
if sha256(TEMPLATE) != EXPECTED_TEMPLATE_HASH:
    raise SystemExit("Template toàn cấp không đúng nền đã khóa: " + sha256(TEMPLATE))
if sha256(LOCK) != EXPECTED_LOCK_HASH:
    raise SystemExit("qd3805_level_lock.json không đúng nền đã khóa: " + sha256(LOCK))
if sha256(NEW_BATCH_SERVICE) != EXPECTED_NEW_BATCH_HASH:
    raise SystemExit("Batch service trong ZIP sai hash.")
if sha256(NEW_TEMPLATE) != EXPECTED_NEW_TEMPLATE_HASH:
    raise SystemExit("Template trong ZIP sai hash.")

integrity, fk, mn_batch, th_batch = db_check()
if integrity.lower() != "ok" or fk:
    raise SystemExit(f"Database không đạt integrity/FK: {integrity}, fk={fk}")
if mn_batch != 0:
    raise SystemExit(f"Đã có {mn_batch} batch MN; dừng để tránh chạy lặp.")
if th_batch != 1:
    raise SystemExit(f"Tiểu học phải có đúng 1 batch đã đóng; hiện có {th_batch}.")

db_before = sha256(DB)

raw = LOCK.read_bytes()
payload = json.loads(raw.decode("utf-8"))
payload = patch_lock(payload)
new_lock_bytes = json.dumps(
    payload,
    ensure_ascii=False,
    indent=2,
    sort_keys=False,
).encode("utf-8")

stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
backup = ROOT / "backups" / f"backup_truoc_phan_loai_dac_thu_MN_{stamp}"
backup.mkdir(parents=True, exist_ok=False)

backup_map = {
    BATCH_SERVICE: backup / BATCH_SERVICE.name,
    TEMPLATE: backup / TEMPLATE.name,
    LOCK: backup / LOCK.name,
}
if MN_RESOLUTION.exists():
    backup_map[MN_RESOLUTION] = backup / MN_RESOLUTION.name

for src, dst in backup_map.items():
    shutil.copy2(src, dst)

resolution_existed = MN_RESOLUTION.exists()

try:
    atomic_write(LOCK, new_lock_bytes)
    shutil.copy2(NEW_BATCH_SERVICE, BATCH_SERVICE)
    shutil.copy2(NEW_TEMPLATE, TEMPLATE)
    MN_RESOLUTION.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(NEW_RESOLUTION, MN_RESOLUTION)

    py_compile.compile(str(BATCH_SERVICE), doraise=True)

    result = smoke()
    counts = result.get("mn_counts") or {}

    if int(result.get("mn_expected") or 0) != 189:
        raise RuntimeError("MN action sau tách đặc thù phải là 189.")
    if int(result.get("mn_mapped") or 0) != 189:
        raise RuntimeError("MN phải ghép đủ 189/189 action thuần toàn trường.")
    if int(result.get("mn_keep") or 0) != 51:
        raise RuntimeError("MN KEEP phải giữ 51.")
    if int(result.get("mn_cross") or 0) != 0:
        raise RuntimeError("Mầm non không được có liên cấp.")
    if int(result.get("mn_same_special") or 0) != 3:
        raise RuntimeError("Phải tách đúng 3 đặc thù cùng cấp.")
    if set(result.get("mn_same_special_ids") or []) != SPECIAL_IDS:
        raise RuntimeError(
            "Danh sách đặc thù cùng cấp không đúng: "
            + json.dumps(result.get("mn_same_special_ids"), ensure_ascii=False)
        )
    if int(result.get("mn_unresolved") or 0) != 1:
        raise RuntimeError("Mầm non vẫn phải giữ đúng 1 dòng QĐ3805 chưa xác định.")
    if int(counts.get("DONE") or 0) != 181:
        raise RuntimeError(
            "Không được thay đổi 181 phương án đã hoàn tất trước: "
            + json.dumps(counts, ensure_ascii=False)
        )
    if int(counts.get("READY") or 0) + int(counts.get("BLOCK") or 0) != 8:
        raise RuntimeError(
            "Sau tách 3 đặc thù, phần còn lại phải đúng 8 phương án thuần chưa hoàn tất: "
            + json.dumps(counts, ensure_ascii=False)
        )

    th_counts = result.get("th_counts") or {}
    if (
        int(th_counts.get("DONE") or 0) != 160
        or int(th_counts.get("READY") or 0) != 0
        or int(th_counts.get("BLOCK") or 0) != 0
        or not bool(result.get("th_previous_batch"))
    ):
        raise RuntimeError(
            "Trạng thái Tiểu học đã đóng bị thay đổi: "
            + json.dumps(th_counts, ensure_ascii=False)
        )

    if sha256(DB) != db_before:
        raise RuntimeError("Hash phocap.db thay đổi ngoài dự kiến.")

    report_dir = ROOT / "exports" / "Phan_Loai_Dac_Thu_MN_QD3805"
    report_dir.mkdir(parents=True, exist_ok=True)
    report = report_dir / f"bao_cao_phan_loai_dac_thu_MN_{stamp}.json"
    report.write_text(json.dumps({
        "installed_at": datetime.now().isoformat(timespec="seconds"),
        "database_unchanged": True,
        "special_same_level": sorted(SPECIAL_IDS),
        "code_patches": CODE_PATCHES,
        "smoke": result,
        "backup": str(backup),
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print()
    print("="*118)
    print("CÀI ĐẶT THÀNH CÔNG - MẦM NON ĐÃ PHÂN LOẠI ĐÚNG")
    print("Liên cấp MN: 0")
    print("Đặc thù cùng cấp tách riêng: 3")
    print("  - QD3805-OP-0141: tiếp nhận điểm lẻ MN Diễn Yên")
    print("  - QD3805-OP-0244: tiếp nhận điểm lẻ Long Xá")
    print("  - QD3805-OP-0704: tiếp nhận 6 lớp MN Hermann Gmeiner")
    print("Action sáp nhập toàn trường MN:", result.get("mn_mapped"), "/", result.get("mn_expected"))
    print("KPI MN:", json.dumps(result.get("mn_counts") or {}, ensure_ascii=False))
    print("Candidate MN:", result.get("mn_candidate"))
    print("BLOCK hiệu lực MN:", result.get("mn_effective_block"))
    print("QĐ3805 chưa xác định: 1 (Mầm non Lượng Minh) - vẫn CHẶN, chưa tự suy đoán.")
    print("Tiểu học: giữ nguyên 160 DONE / 0 READY / 0 BLOCK.")
    print("Database: KHÔNG THAY ĐỔI")
    print("Bộ cài KHÔNG thực hiện sáp nhập.")
    print("Backup:", backup)
    print("Báo cáo:", report)
    print("="*118)

except Exception as exc:
    try:
        shutil.copy2(backup / BATCH_SERVICE.name, BATCH_SERVICE)
        shutil.copy2(backup / TEMPLATE.name, TEMPLATE)
        shutil.copy2(backup / LOCK.name, LOCK)
        if resolution_existed:
            shutil.copy2(backup / MN_RESOLUTION.name, MN_RESOLUTION)
        elif MN_RESOLUTION.exists():
            MN_RESOLUTION.unlink()
    except Exception:
        pass

    print("="*118)
    print("DỪNG AN TOÀN - ĐÃ KHÔI PHỤC CÁC FILE CŨ")
    print("Lỗi:", exc)
    print("Database: KHÔNG CHỦ ĐỘNG GHI")
    print("="*118)
    raise SystemExit(1)
