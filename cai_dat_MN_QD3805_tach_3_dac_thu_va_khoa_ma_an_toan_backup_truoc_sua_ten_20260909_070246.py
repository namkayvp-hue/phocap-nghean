# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import json
import os
import py_compile
import re
import shutil
import sqlite3
import subprocess
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

ROOT = Path(r"C:\PhoCap")
HERE = Path(__file__).resolve().parent

DB = ROOT / "data" / "phocap.db"
SERVICE = ROOT / "app" / "services" / "school_merger_level_batch_service.py"
REGISTRY_SERVICE = ROOT / "app" / "services" / "school_merger_official_registry.py"
TEMPLATE = ROOT / "app" / "templates" / "data_tools" / "school_merger_level_batch.html"
LOCK = ROOT / "data" / "school_merger_registry" / "qd3805_level_lock.json"
MN_RESOLUTION = ROOT / "data" / "school_merger_registry" / "qd3805_mn_resolution.json"

NEW_SERVICE = HERE / "school_merger_level_batch_service.py"
NEW_TEMPLATE = HERE / "school_merger_level_batch.html"
NEW_RESOLUTION = HERE / "qd3805_mn_resolution.json"

EXPECTED_SERVICE_HASH = "ea5b86cf02395d960f53011352bc7dd4450c556710383c912b473dd21c7d5cf2"
EXPECTED_TEMPLATE_HASH = "72ac5b4cc27001fbbca6ec783772cc7e9c41e3ad32bbcbc28cc211114b178708"
EXPECTED_REGISTRY_SERVICE_HASH = "12cb62d3cd9cc7e2834b5658506c8825943a9c8820f0e7b89a7b647e47db4264"
EXPECTED_LOCK_HASH = "8e581eaddd0e2b8f482f3ab272d804d06155268fc3a755fd5a20aedf9067738a"
EXPECTED_NEW_SERVICE_HASH = "6e16d39e75c08bfeef484e0a565d5f694bc750306210b0849fcc5f969de747be"
EXPECTED_NEW_TEMPLATE_HASH = "24b0429e4dc293ded39d77e72bfea39f25176f2c1331f91863d666cd486828b0"

SPECIAL_IDS = {
    "QD3805-OP-0141",
    "QD3805-OP-0244",
    "QD3805-OP-0704",
}

MISSING_ROWS = {
    "QD3805-OP-0410": 802,
    "QD3805-OP-0282": 537,
    "QD3805-OP-0449": 880,
    "QD3805-OP-0592": 1148,
    "QD3805-OP-0600": 1169,
}

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def atomic_write(path: Path, data: bytes) -> None:
    tmp = path.with_name(path.name + ".mn-safe.tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)

def norm_name(value) -> str:
    s = str(value or "").strip().lower().replace("đ", "d")
    s = "".join(
        ch for ch in unicodedata.normalize("NFD", s)
        if unicodedata.category(ch) != "Mn"
    )
    s = re.sub(r"\btruong\b", " ", s)
    s = re.sub(r"\bmam\s*non\b", " ", s)
    s = re.sub(r"\bmn\b", " ", s)
    s = re.sub(r"\btt\b", " thi tran ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())

def compatible_name(expected: str, actual: str) -> bool:
    a = norm_name(expected)
    b = norm_name(actual)
    if not a or not b:
        return False
    if a == b:
        return True
    # Chỉ cho phép sai khác duy nhất một hậu tố số (ví dụ Thanh Đức / Thanh Đức 1).
    if b.startswith(a + " ") and b[len(a)+1:].isdigit():
        return True
    if a.startswith(b + " ") and a[len(b)+1:].isdigit():
        return True
    return False

def connect_ro():
    con = sqlite3.connect(DB.resolve().as_uri() + "?mode=ro", uri=True, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only=ON")
    con.execute("PRAGMA foreign_keys=ON")
    return con

def db_check():
    with connect_ro() as con:
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

def current_preview():
    code = r"""
import json
from app.services.school_merger_level_batch_service import build_level_batch_preview
mn = build_level_batch_preview(school_year_id=2, level_code="MN")
th = build_level_batch_preview(school_year_id=2, level_code="TH")
print(json.dumps({
    "mn_counts": mn.get("counts"),
    "mn_effective": mn.get("effective_block_count"),
    "mn_expected": mn.get("registry_action_expected_count"),
    "mn_mapped": mn.get("registry_action_mapped_count"),
    "mn_keep": mn.get("registry_keep_expected_count"),
    "mn_cross": mn.get("excluded_cross_level_count"),
    "mn_same_special": mn.get("excluded_same_level_special_count", 0),
    "mn_action_total": mn.get("registry_action_total_count", mn.get("registry_action_expected_count")),
    "mn_unresolved": mn.get("registry_unresolved_count"),
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

def school_candidates(con, expected_name: str):
    # Ưu tiên dữ liệu mạng lưới MN 2025-2026 đã nhập vào DB.
    year = con.execute(
        "SELECT id FROM school_years "
        "WHERE REPLACE(REPLACE(code,'–','-'),'—','-')='2025-2026' LIMIT 1"
    ).fetchone()
    if year is None:
        raise RuntimeError("Không tìm thấy năm học nguồn 2025-2026.")
    yid = int(year["id"])

    rows = con.execute(
        "SELECT DISTINCT s.id,s.code,s.name,s.is_active,"
        "c.name AS commune_name,sny.source_name "
        "FROM school_network_year_data sny "
        "JOIN schools s ON s.id=sny.school_id "
        "LEFT JOIN communes c ON c.id=s.commune_id "
        "WHERE sny.school_year_id=? AND UPPER(sny.level_code)='MN' "
        "AND COALESCE(TRIM(s.code),'')<>'' "
        "ORDER BY s.id",
        (yid,),
    ).fetchall()

    exact = [dict(r) for r in rows if compatible_name(expected_name, r["name"])]
    return exact

def resolve_missing_codes(lock_payload: dict):
    ops = {
        str(x.get("operation_id") or ""): x
        for x in (lock_payload.get("operations") or [])
        if isinstance(x, dict)
    }
    resolved = {}

    with connect_ro() as con:
        for op_id, excel_row in MISSING_ROWS.items():
            op = ops.get(op_id)
            if op is None:
                raise RuntimeError("Không tìm thấy " + op_id)

            target_row = None
            for src in op.get("source_schools") or []:
                if not isinstance(src, dict):
                    continue
                try:
                    row = int(src.get("excel_row"))
                except Exception:
                    continue
                if row == int(excel_row):
                    target_row = src
                    break
            if target_row is None:
                raise RuntimeError(f"{op_id} không tìm thấy excel_row {excel_row}.")

            old_codes = [
                str(x or "").strip()
                for x in (target_row.get("codes") or [])
                if str(x or "").strip()
            ]
            if old_codes:
                raise RuntimeError(
                    f"{op_id} row {excel_row} không còn thiếu mã: {old_codes}"
                )

            expected_name = str(target_row.get("name") or "")
            candidates = school_candidates(con, expected_name)
            if len(candidates) != 1:
                raise RuntimeError(
                    f"{op_id} / {expected_name}: cần đúng 1 trường MN 2025-2026 "
                    f"khớp tên trong DB, nhưng tìm thấy {len(candidates)}. "
                    f"Chi tiết={json.dumps(candidates, ensure_ascii=False)}"
                )

            cand = candidates[0]
            code = str(cand.get("code") or "").strip()
            if not code:
                raise RuntimeError(f"{op_id} / {expected_name}: trường DB chưa có mã.")

            target_row["codes"] = [code]

            # Nếu dòng thiếu mã chính là trường đích và target_codes đang trống,
            # khóa target bằng chính mã vừa xác định từ dữ liệu MN 2025-2026.
            if (
                not [
                    str(x or "").strip()
                    for x in (op.get("target_codes") or [])
                    if str(x or "").strip()
                ]
                and compatible_name(
                    str(op.get("target_text") or ""),
                    expected_name,
                )
            ):
                op["target_codes"] = [code]

            # Với operation đã có target code và dòng thiếu mã chính là target theo tên,
            # mã DB phải trùng target đã khóa; nếu khác thì dừng.
            existing_target = [
                str(x or "").strip()
                for x in (op.get("target_codes") or [])
                if str(x or "").strip()
            ]
            if (
                existing_target
                and compatible_name(str(op.get("target_text") or ""), expected_name)
                and code not in existing_target
            ):
                raise RuntimeError(
                    f"{op_id}: mã DB {code} của {expected_name} "
                    f"khác target_codes QĐ3805 {existing_target}."
                )

            all_codes = []
            for src in op.get("source_schools") or []:
                for c in src.get("codes") or []:
                    c = str(c or "").strip()
                    if c and c not in all_codes:
                        all_codes.append(c)
            op["source_codes"] = all_codes

            resolved[op_id] = {
                "excel_row": excel_row,
                "expected_name": expected_name,
                "resolved_school_id": cand.get("id"),
                "resolved_school_name": cand.get("name"),
                "resolved_commune": cand.get("commune_name"),
                "resolved_code": code,
                "source_name": cand.get("source_name"),
            }

    return lock_payload, resolved

print("="*118)
print("MẦM NON QĐ3805 - BẢN ĐÚNG NỀN HIỆN TẠI")
print("Tách 3 ĐẶC THÙ CÙNG CẤP + khóa an toàn 5 mã còn thiếu")
print("KHÔNG thực hiện sáp nhập. KHÔNG sửa Excel nguồn. KHÔNG ghi phocap.db.")
print("="*118)

for p in (DB, SERVICE, REGISTRY_SERVICE, TEMPLATE, LOCK,
          NEW_SERVICE, NEW_TEMPLATE, NEW_RESOLUTION):
    if not p.exists():
        raise SystemExit("Thiếu file bắt buộc: " + str(p))

checks = {
    "batch_service": (sha256(SERVICE), EXPECTED_SERVICE_HASH),
    "official_registry_service": (sha256(REGISTRY_SERVICE), EXPECTED_REGISTRY_SERVICE_HASH),
    "template": (sha256(TEMPLATE), EXPECTED_TEMPLATE_HASH),
    "level_lock": (sha256(LOCK), EXPECTED_LOCK_HASH),
}
for label, pair in checks.items():
    if pair[0] != pair[1]:
        raise SystemExit(
            f"{label} không đúng nền đã khóa. Hiện={pair[0]} / cần={pair[1]}"
        )

if sha256(NEW_SERVICE) != EXPECTED_NEW_SERVICE_HASH:
    raise SystemExit("Service mới trong ZIP sai hash.")
if sha256(NEW_TEMPLATE) != EXPECTED_NEW_TEMPLATE_HASH:
    raise SystemExit("Template mới trong ZIP sai hash.")

integrity, fk, mn_batch, th_batch = db_check()
if integrity.lower() != "ok" or fk:
    raise SystemExit(f"Database không đạt integrity/FK: {integrity}, fk={fk}")
if mn_batch != 0:
    raise SystemExit(f"Đã có {mn_batch} batch Mầm non; dừng để tránh chạy lặp.")
if th_batch != 1:
    raise SystemExit(f"Tiểu học phải có đúng 1 batch đã đóng; hiện có {th_batch}.")

before_preview = current_preview()
bc = before_preview.get("mn_counts") or {}
if (
    int(bc.get("KEEP") or 0) != 51
    or int(bc.get("DONE") or 0) != 181
    or int(bc.get("READY") or 0) != 0
    or int(bc.get("BLOCK") or 0) != 11
    or int(before_preview.get("mn_effective") or 0) != 12
):
    raise SystemExit(
        "Nền Mầm non trước cài không còn đúng 51 KEEP / 181 DONE / "
        "0 READY / 11 BLOCK / 12 BLOCK hiệu lực. Dừng an toàn. "
        + json.dumps(before_preview, ensure_ascii=False)
    )

thc = before_preview.get("th_counts") or {}
if (
    int(thc.get("DONE") or 0) != 160
    or int(thc.get("READY") or 0) != 0
    or int(thc.get("BLOCK") or 0) != 0
    or not bool(before_preview.get("th_previous_batch"))
):
    raise SystemExit(
        "Tiểu học đã đóng không đúng trạng thái kỳ vọng: "
        + json.dumps(before_preview, ensure_ascii=False)
    )

db_before = sha256(DB)
lock_payload = json.loads(LOCK.read_text(encoding="utf-8"))
lock_payload, resolved_codes = resolve_missing_codes(lock_payload)
new_lock_bytes = json.dumps(
    lock_payload,
    ensure_ascii=False,
    indent=2,
    sort_keys=False,
).encode("utf-8")

stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
backup = ROOT / "backups" / f"backup_truoc_tach_3_dac_thu_MN_{stamp}"
backup.mkdir(parents=True, exist_ok=False)

backup_items = [SERVICE, TEMPLATE, LOCK]
resolution_existed = MN_RESOLUTION.exists()
if resolution_existed:
    backup_items.append(MN_RESOLUTION)

for src in backup_items:
    shutil.copy2(src, backup / src.name)

try:
    atomic_write(LOCK, new_lock_bytes)
    shutil.copy2(NEW_SERVICE, SERVICE)
    shutil.copy2(NEW_TEMPLATE, TEMPLATE)
    MN_RESOLUTION.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(NEW_RESOLUTION, MN_RESOLUTION)
    py_compile.compile(str(SERVICE), doraise=True)

    after = current_preview()
    counts = after.get("mn_counts") or {}

    if int(after.get("mn_action_total") or 0) != 192:
        raise RuntimeError("Tổng phương án cần tác động MN phải giữ 192.")
    if int(after.get("mn_expected") or 0) != 189:
        raise RuntimeError("Batch sáp nhập toàn trường MN phải còn 189 action.")
    if int(after.get("mn_mapped") or 0) != 189:
        raise RuntimeError("Engine phải ghép đủ 189/189 action toàn trường.")
    if int(after.get("mn_keep") or 0) != 51:
        raise RuntimeError("MN KEEP phải giữ 51.")
    if int(after.get("mn_cross") or 0) != 0:
        raise RuntimeError("Mầm non không được xuất hiện liên cấp.")
    if int(after.get("mn_same_special") or 0) != 3:
        raise RuntimeError("Phải tách đúng 3 đặc thù cùng cấp.")
    if int(after.get("mn_unresolved") or 0) != 1:
        raise RuntimeError("Phải giữ đúng 1 dòng QĐ3805 chưa xác định.")
    if int(counts.get("DONE") or 0) != 181:
        raise RuntimeError("181 phương án đã hoàn tất trước không được thay đổi.")
    if int(counts.get("READY") or 0) + int(counts.get("BLOCK") or 0) != 8:
        raise RuntimeError(
            "Sau khi tách 3 đặc thù phải còn đúng 8 action toàn trường chưa hoàn tất: "
            + json.dumps(counts, ensure_ascii=False)
        )

    th_counts = after.get("th_counts") or {}
    if (
        int(th_counts.get("DONE") or 0) != 160
        or int(th_counts.get("READY") or 0) != 0
        or int(th_counts.get("BLOCK") or 0) != 0
        or not bool(after.get("th_previous_batch"))
    ):
        raise RuntimeError(
            "Trạng thái Tiểu học đã đóng bị thay đổi: "
            + json.dumps(after, ensure_ascii=False)
        )

    if sha256(DB) != db_before:
        raise RuntimeError("Hash phocap.db thay đổi ngoài dự kiến.")

    report_dir = ROOT / "exports" / "Tach_3_Dac_Thu_MN_QD3805"
    report_dir.mkdir(parents=True, exist_ok=True)
    report = report_dir / f"bao_cao_tach_3_dac_thu_MN_{stamp}.json"
    report.write_text(json.dumps({
        "installed_at": datetime.now().isoformat(timespec="seconds"),
        "database_unchanged": True,
        "resolved_codes_from_db_2025_2026": resolved_codes,
        "special_same_level": sorted(SPECIAL_IDS),
        "before_preview": before_preview,
        "after_preview": after,
        "backup": str(backup),
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print()
    print("="*118)
    print("CÀI ĐẶT THÀNH CÔNG - MẦM NON ĐÃ PHÂN LOẠI ĐÚNG TRÊN NỀN HIỆN TẠI")
    print("Mầm non liên cấp: 0")
    print("Đặc thù cùng cấp tách riêng: 3")
    print("  - OP-0141: tiếp nhận điểm lẻ MN Diễn Yên")
    print("  - OP-0244: tiếp nhận điểm lẻ Long Xá")
    print("  - OP-0704: tiếp nhận 6 lớp MN Hermann Gmeiner")
    print("Đã khóa 5 mã thiếu bằng DB MN 2025-2026:")
    for op_id, item in resolved_codes.items():
        print(
            f"  - {op_id} row {item['excel_row']}: "
            f"{item['resolved_school_name']} -> {item['resolved_code']}"
        )
    print("KPI MN sau cài:", json.dumps(after.get("mn_counts") or {}, ensure_ascii=False))
    print("Candidate MN:", after.get("mn_candidate"))
    print("BLOCK hiệu lực MN:", after.get("mn_effective"))
    print("QĐ3805 chưa xác định: 1 - vẫn giữ CHẶN, không tự suy đoán.")
    print("Tiểu học: giữ nguyên 160 DONE / 0 READY / 0 BLOCK.")
    print("Database: KHÔNG THAY ĐỔI")
    print("Bộ cài KHÔNG thực hiện sáp nhập.")
    print("Backup:", backup)
    print("Báo cáo:", report)
    print("="*118)

except Exception as exc:
    try:
        shutil.copy2(backup / SERVICE.name, SERVICE)
        shutil.copy2(backup / TEMPLATE.name, TEMPLATE)
        shutil.copy2(backup / LOCK.name, LOCK)
        if resolution_existed:
            shutil.copy2(backup / MN_RESOLUTION.name, MN_RESOLUTION)
        elif MN_RESOLUTION.exists():
            MN_RESOLUTION.unlink()
    except Exception:
        pass
    print("="*118)
    print("DỪNG AN TOÀN - ĐÃ KHÔI PHỤC TOÀN BỘ FILE CŨ")
    print("Lỗi:", exc)
    print("Database: KHÔNG CHỦ ĐỘNG GHI")
    print("="*118)
    raise SystemExit(1)
