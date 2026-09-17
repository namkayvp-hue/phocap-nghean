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
BATCH_SERVICE = ROOT / "app" / "services" / "school_merger_level_batch_service.py"
REGISTRY_SERVICE = ROOT / "app" / "services" / "school_merger_official_registry.py"
TEMPLATE = ROOT / "app" / "templates" / "data_tools" / "school_merger_level_batch.html"
LOCK = ROOT / "data" / "school_merger_registry" / "qd3805_level_lock.json"
MN_RESOLUTION = ROOT / "data" / "school_merger_registry" / "qd3805_mn_resolution.json"

NEW_BATCH_SERVICE = HERE / "school_merger_level_batch_service.py"
NEW_TEMPLATE = HERE / "school_merger_level_batch.html"
NEW_RESOLUTION = HERE / "qd3805_mn_resolution.json"

EXPECTED_BATCH_HASH = "ea5b86cf02395d960f53011352bc7dd4450c556710383c912b473dd21c7d5cf2"
EXPECTED_REGISTRY_SERVICE_HASH = "12cb62d3cd9cc7e2834b5658506c8825943a9c8820f0e7b89a7b647e47db4264"
EXPECTED_TEMPLATE_HASH = "72ac5b4cc27001fbbca6ec783772cc7e9c41e3ad32bbcbc28cc211114b178708"
EXPECTED_LOCK_HASH = "8e581eaddd0e2b8f482f3ab272d804d06155268fc3a755fd5a20aedf9067738a"

EXPECTED_NEW_BATCH_HASH = "abff58a7d0d9e0d74c57ed998d4144b2fc1f9abeb42ce25f4cf779977083f048"
EXPECTED_NEW_TEMPLATE_HASH = "519f8e69ca934d86f94e0b2d23cba2bfe7d0d294eecf14df960f5d6cc9ab5028"
EXPECTED_NEW_RESOLUTION_HASH = "ecf660e12a70b809337434cf89ac331a0825d6214bb5b6ef244779b14df92722"

SPECIAL_IDS = {
    "QD3805-OP-0141",
    "QD3805-OP-0244",
    "QD3805-OP-0704",
}

# 5 mã đã đối chiếu lại từ file mạng lưới Mầm non 2025-2026.
CODE_PATCHES = {
    "QD3805-OP-0410": {
        "excel_row": 802,
        "code": "40415304",
        "school_name_piece": "Tiền Phong",
        "commune_piece": "Tiền Phong",
        "set_target_if_empty": True,
    },
    "QD3805-OP-0282": {
        "excel_row": 537,
        "code": "40417301",
        "school_name_piece": "Mường Xén",
        "commune_piece": "Mường Xén",
        "set_target_if_empty": False,
    },
    "QD3805-OP-0449": {
        "excel_row": 880,
        "code": "40420313",
        "school_name_piece": "Châu Thái",
        "commune_piece": "Mường Ham",
        "set_target_if_empty": False,
    },
    "QD3805-OP-0592": {
        "excel_row": 1148,
        "code": "40428306",
        "school_name_piece": "Thanh Đức",
        "commune_piece": "Hạnh Lâm",
        "set_target_if_empty": False,
    },
    "QD3805-OP-0600": {
        "excel_row": 1169,
        "code": "40428320",
        "school_name_piece": "Thanh Hà",
        "commune_piece": "Kim Bảng",
        "set_target_if_empty": False,
    },
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def norm(value: object) -> str:
    text = str(value or "").strip().lower().replace("đ", "d")
    text = "".join(
        ch
        for ch in unicodedata.normalize("NFD", text)
        if unicodedata.category(ch) != "Mn"
    )
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def atomic_write(path: Path, data: bytes) -> None:
    tmp = path.with_name(path.name + ".mn_qd3805.tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def read_db_state() -> dict:
    con = sqlite3.connect(
        DB.resolve().as_uri() + "?mode=ro",
        uri=True,
        timeout=30,
    )
    con.row_factory = sqlite3.Row
    try:
        con.execute("PRAGMA query_only=ON")
        con.execute("PRAGMA foreign_keys=ON")
        integrity = str(con.execute("PRAGMA integrity_check").fetchone()[0])
        fk_rows = con.execute("PRAGMA foreign_key_check").fetchall()

        table = con.execute(
            "SELECT 1 FROM sqlite_master "
            "WHERE type='table' AND name='school_merger_level_batches'"
        ).fetchone()

        mn_batches = 0
        th_batches = 0
        if table is not None:
            mn_batches = int(
                con.execute(
                    "SELECT COUNT(*) FROM school_merger_level_batches "
                    "WHERE school_year_id=2 AND level_code='MN'"
                ).fetchone()[0]
            )
            th_batches = int(
                con.execute(
                    "SELECT COUNT(*) FROM school_merger_level_batches "
                    "WHERE school_year_id=2 AND level_code='TH'"
                ).fetchone()[0]
            )

        code_checks = {}
        for op_id, cfg in CODE_PATCHES.items():
            rows = con.execute(
                "SELECT s.id,s.code,s.name,s.is_active,c.name AS commune_name "
                "FROM schools s LEFT JOIN communes c ON c.id=s.commune_id "
                "WHERE s.code=? ORDER BY s.id",
                (cfg["code"],),
            ).fetchall()
            code_checks[op_id] = [dict(x) for x in rows]

        return {
            "integrity": integrity,
            "foreign_key_errors": len(fk_rows),
            "mn_batches": mn_batches,
            "th_batches": th_batches,
            "code_checks": code_checks,
        }
    finally:
        con.close()


def validate_code_checks(state: dict) -> None:
    for op_id, cfg in CODE_PATCHES.items():
        rows = list((state.get("code_checks") or {}).get(op_id) or [])
        if len(rows) != 1:
            raise RuntimeError(
                f"{op_id}: mã {cfg['code']} phải khớp đúng 1 trường DB; "
                f"hiện khớp {len(rows)}."
            )

        row = rows[0]
        if norm(cfg["school_name_piece"]) not in norm(row.get("name")):
            raise RuntimeError(
                f"{op_id}: mã {cfg['code']} đang trỏ tới tên DB không đúng "
                f"dự kiến: {row.get('name')}"
            )
        if norm(cfg["commune_piece"]) not in norm(row.get("commune_name")):
            raise RuntimeError(
                f"{op_id}: mã {cfg['code']} đang thuộc địa bàn DB không đúng "
                f"dự kiến: {row.get('commune_name')}"
            )


def patch_lock(payload: dict) -> dict:
    operations = {
        str(x.get("operation_id") or ""): x
        for x in (payload.get("operations") or [])
        if isinstance(x, dict)
    }

    for op_id, cfg in CODE_PATCHES.items():
        op = operations.get(op_id)
        if op is None:
            raise RuntimeError("Không tìm thấy operation " + op_id)

        if str(op.get("batch") or "").upper() != "MN":
            raise RuntimeError(op_id + " không còn là batch MN.")

        wanted_row = int(cfg["excel_row"])
        hit = None
        for src in op.get("source_schools") or []:
            if not isinstance(src, dict):
                continue
            try:
                row = int(src.get("excel_row"))
            except Exception:
                continue
            if row == wanted_row:
                hit = src
                break

        if hit is None:
            raise RuntimeError(
                f"{op_id}: không tìm thấy Excel row {wanted_row}."
            )

        if norm(cfg["school_name_piece"]) not in norm(hit.get("name")):
            raise RuntimeError(
                f"{op_id}: row {wanted_row} không đúng trường dự kiến: "
                f"{hit.get('name')}"
            )

        current_codes = [
            str(x or "").strip()
            for x in (hit.get("codes") or [])
            if str(x or "").strip()
        ]
        if current_codes and cfg["code"] not in current_codes:
            raise RuntimeError(
                f"{op_id}: row {wanted_row} đã có mã khác "
                f"{current_codes}; không tự ghi đè."
            )
        hit["codes"] = [cfg["code"]]

        target_codes = [
            str(x or "").strip()
            for x in (op.get("target_codes") or [])
            if str(x or "").strip()
        ]
        if cfg["set_target_if_empty"]:
            if target_codes and cfg["code"] not in target_codes:
                raise RuntimeError(
                    f"{op_id}: target_codes hiện có {target_codes}, "
                    "không tự ghi đè."
                )
            if not target_codes:
                op["target_codes"] = [cfg["code"]]

    return payload


def smoke_preview() -> dict:
    code = r'''
import json
from app.services.school_merger_level_batch_service import build_level_batch_preview

mn = build_level_batch_preview(school_year_id=2, level_code="MN")
th = build_level_batch_preview(school_year_id=2, level_code="TH")

print(json.dumps({
    "mn_counts": mn.get("counts"),
    "mn_expected": mn.get("registry_action_expected_count"),
    "mn_mapped": mn.get("registry_action_mapped_count"),
    "mn_keep": mn.get("registry_keep_expected_count"),
    "mn_unresolved": mn.get("registry_unresolved_count"),
    "mn_cross": mn.get("excluded_cross_level_count"),
    "mn_same_special": mn.get("excluded_same_level_special_count", 0),
    "mn_same_special_ids": sorted(
        str(x.get("operation_id") or "")
        for x in (mn.get("excluded_same_level_special") or [])
    ),
    "mn_effective_block": mn.get("effective_block_count"),
    "mn_candidate": mn.get("candidate_count"),
    "mn_ready_for_execution": bool(mn.get("ready_for_execution")),
    "mn_previous_batch": bool(mn.get("previous_batch")),
    "th_counts": th.get("counts"),
    "th_previous_batch": bool(th.get("previous_batch")),
}, ensure_ascii=True))
'''
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"

    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=360,
        env=env,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr or proc.stdout)

    lines = [x for x in (proc.stdout or "").splitlines() if x.strip()]
    if not lines:
        raise RuntimeError("Smoke preview không trả dữ liệu.")
    return json.loads(lines[-1])


def validate_preflight(pre: dict) -> None:
    counts = pre.get("mn_counts") or {}
    expected = {
        "KEEP": 51,
        "DONE": 181,
        "READY": 0,
        "BLOCK": 11,
    }
    if {k: int(counts.get(k) or 0) for k in expected} != expected:
        raise RuntimeError(
            "Nền KPI MN không còn đúng trạng thái đã xác nhận: "
            + json.dumps(counts, ensure_ascii=False)
        )
    if int(pre.get("mn_expected") or 0) != 192:
        raise RuntimeError("Nền MN phải có 192 action trước khi tách đặc thù.")
    if int(pre.get("mn_mapped") or 0) != 192:
        raise RuntimeError("Nền MN phải ghép đủ 192/192 trước khi cài.")
    if int(pre.get("mn_keep") or 0) != 51:
        raise RuntimeError("Nền MN phải có 51 KEEP.")
    if int(pre.get("mn_unresolved") or 0) != 1:
        raise RuntimeError("Nền MN phải còn đúng 1 dòng QĐ3805 chưa xác định.")
    if int(pre.get("mn_cross") or 0) != 0:
        raise RuntimeError("Mầm non không được có liên cấp.")
    if int(pre.get("mn_effective_block") or 0) != 12:
        raise RuntimeError("Nền MN phải có BLOCK hiệu lực = 12.")
    if bool(pre.get("mn_previous_batch")):
        raise RuntimeError("Đã có batch MN; tuyệt đối không chạy lại.")

    th = pre.get("th_counts") or {}
    if (
        int(th.get("DONE") or 0) != 160
        or int(th.get("READY") or 0) != 0
        or int(th.get("BLOCK") or 0) != 0
        or not bool(pre.get("th_previous_batch"))
    ):
        raise RuntimeError(
            "Tiểu học đã đóng không còn đúng 160 DONE / 0 READY / 0 BLOCK."
        )


def validate_postflight(post: dict) -> None:
    counts = post.get("mn_counts") or {}

    if int(post.get("mn_expected") or 0) != 189:
        raise RuntimeError(
            f"Sau tách 3 đặc thù, action MN phải là 189; "
            f"hiện {post.get('mn_expected')}."
        )
    if int(post.get("mn_mapped") or 0) != 189:
        raise RuntimeError(
            f"Sau tách đặc thù, engine phải ghép đủ 189/189; "
            f"hiện {post.get('mn_mapped')}/189."
        )
    if int(post.get("mn_keep") or 0) != 51:
        raise RuntimeError("MN KEEP phải giữ nguyên 51.")
    if int(post.get("mn_cross") or 0) != 0:
        raise RuntimeError("Mầm non vẫn xuất hiện liên cấp sau cài.")
    if int(post.get("mn_same_special") or 0) != 3:
        raise RuntimeError("Phải tách đúng 3 đặc thù cùng cấp.")
    if set(post.get("mn_same_special_ids") or []) != SPECIAL_IDS:
        raise RuntimeError(
            "Danh sách đặc thù cùng cấp không đúng: "
            + json.dumps(post.get("mn_same_special_ids"), ensure_ascii=False)
        )
    if int(post.get("mn_unresolved") or 0) != 1:
        raise RuntimeError(
            "Mầm non vẫn phải giữ 1 dòng QĐ3805 chưa xác định; "
            "không được tự suy đoán."
        )
    if int(counts.get("KEEP") or 0) != 51:
        raise RuntimeError("KPI KEEP MN không còn 51.")
    if int(counts.get("DONE") or 0) != 181:
        raise RuntimeError(
            "181 phương án MN đã hoàn tất trước không được thay đổi."
        )
    if int(counts.get("READY") or 0) + int(counts.get("BLOCK") or 0) != 8:
        raise RuntimeError(
            "Sau khi tách 3 đặc thù, phải còn đúng 8 action toàn trường "
            "chưa hoàn tất: "
            + json.dumps(counts, ensure_ascii=False)
        )
    if bool(post.get("mn_previous_batch")):
        raise RuntimeError("Không được phát sinh batch MN trong bước chuẩn bị.")

    th = post.get("th_counts") or {}
    if (
        int(th.get("DONE") or 0) != 160
        or int(th.get("READY") or 0) != 0
        or int(th.get("BLOCK") or 0) != 0
        or not bool(post.get("th_previous_batch"))
    ):
        raise RuntimeError(
            "Trạng thái Tiểu học đã đóng bị thay đổi ngoài dự kiến."
        )


print("=" * 118)
print("MẦM NON QĐ3805 - CÀI TRÊN ĐÚNG NỀN HIỆN TẠI 17:19")
print("Tách 3 đặc thù CÙNG CẤP + khóa 5 mã trường đã đối chiếu")
print("Database:", DB)
print("KHÔNG thực hiện sáp nhập. KHÔNG sửa Excel nguồn.")
print("=" * 118)

for path in (
    DB,
    BATCH_SERVICE,
    REGISTRY_SERVICE,
    TEMPLATE,
    LOCK,
    NEW_BATCH_SERVICE,
    NEW_TEMPLATE,
    NEW_RESOLUTION,
):
    if not path.exists():
        raise SystemExit("Thiếu file bắt buộc: " + str(path))

checks = {
    "batch_service": (BATCH_SERVICE, EXPECTED_BATCH_HASH),
    "official_registry": (REGISTRY_SERVICE, EXPECTED_REGISTRY_SERVICE_HASH),
    "template": (TEMPLATE, EXPECTED_TEMPLATE_HASH),
    "level_lock": (LOCK, EXPECTED_LOCK_HASH),
}
for label, (path, expected_hash) in checks.items():
    current = sha256(path)
    if current != expected_hash:
        raise SystemExit(
            f"{label} không đúng nền 17:19 đã khóa. "
            f"Hash hiện tại: {current}"
        )

if sha256(NEW_BATCH_SERVICE) != EXPECTED_NEW_BATCH_HASH:
    raise SystemExit("Batch service đi kèm ZIP không đúng hash.")
if sha256(NEW_TEMPLATE) != EXPECTED_NEW_TEMPLATE_HASH:
    raise SystemExit("Template đi kèm ZIP không đúng hash.")
if sha256(NEW_RESOLUTION) != EXPECTED_NEW_RESOLUTION_HASH:
    raise SystemExit("MN resolution đi kèm ZIP không đúng hash.")

if MN_RESOLUTION.exists():
    raise SystemExit(
        "Đã tồn tại qd3805_mn_resolution.json ngoài nền 17:19. "
        "Dừng để tránh ghi đè thay đổi mới."
    )

db_state = read_db_state()
if str(db_state["integrity"]).lower() != "ok":
    raise SystemExit(
        "Database integrity_check không đạt: " + str(db_state["integrity"])
    )
if int(db_state["foreign_key_errors"]) != 0:
    raise SystemExit(
        "Database có lỗi foreign key: "
        + str(db_state["foreign_key_errors"])
    )
if int(db_state["mn_batches"]) != 0:
    raise SystemExit(
        f"Đã tồn tại {db_state['mn_batches']} batch MN; dừng để tránh chạy lặp."
    )
if int(db_state["th_batches"]) != 1:
    raise SystemExit(
        f"Tiểu học phải có đúng 1 batch đã đóng; hiện có "
        f"{db_state['th_batches']}."
    )
validate_code_checks(db_state)

print("Kiểm tra nền trước cài...")
pre = smoke_preview()
validate_preflight(pre)
print("  KPI MN trước cài:", json.dumps(pre["mn_counts"], ensure_ascii=False))
print("  QĐ3805 MN:", pre["mn_mapped"], "/", pre["mn_expected"])
print("  Tiểu học: 160 DONE / 0 READY / 0 BLOCK")

db_hash_before = sha256(DB)

lock_payload = json.loads(LOCK.read_text(encoding="utf-8"))
patched_lock = patch_lock(lock_payload)
new_lock_bytes = json.dumps(
    patched_lock,
    ensure_ascii=False,
    indent=2,
).encode("utf-8")

stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
backup = (
    ROOT
    / "backups"
    / f"backup_truoc_phan_loai_dac_thu_va_khoa_ma_MN_{stamp}"
)
backup.mkdir(parents=True, exist_ok=False)

backup_batch = backup / BATCH_SERVICE.name
backup_template = backup / TEMPLATE.name
backup_lock = backup / LOCK.name

shutil.copy2(BATCH_SERVICE, backup_batch)
shutil.copy2(TEMPLATE, backup_template)
shutil.copy2(LOCK, backup_lock)

try:
    atomic_write(LOCK, new_lock_bytes)
    shutil.copy2(NEW_BATCH_SERVICE, BATCH_SERVICE)
    shutil.copy2(NEW_TEMPLATE, TEMPLATE)
    shutil.copy2(NEW_RESOLUTION, MN_RESOLUTION)

    py_compile.compile(str(BATCH_SERVICE), doraise=True)

    print("Kiểm tra sau cài...")
    post = smoke_preview()
    validate_postflight(post)

    if sha256(DB) != db_hash_before:
        raise RuntimeError(
            "Hash phocap.db thay đổi trong bước chỉ chuẩn bị; dừng và rollback file."
        )

    after_state = read_db_state()
    if str(after_state["integrity"]).lower() != "ok":
        raise RuntimeError("Database integrity_check sau cài không đạt.")
    if int(after_state["foreign_key_errors"]) != 0:
        raise RuntimeError("Database phát sinh lỗi foreign key sau cài.")
    if int(after_state["mn_batches"]) != 0:
        raise RuntimeError("Bước chuẩn bị không được tạo batch MN.")

    report_dir = (
        ROOT
        / "exports"
        / "Phan_Loai_Dac_Thu_Va_Khoa_Ma_MN_QD3805"
    )
    report_dir.mkdir(parents=True, exist_ok=True)
    report = report_dir / f"bao_cao_cai_MN_dung_nen_171928_{stamp}.json"
    report.write_text(
        json.dumps(
            {
                "installed_at": datetime.now().isoformat(timespec="seconds"),
                "database_unchanged": True,
                "baseline_hashes": {
                    k: expected
                    for k, (_, expected) in checks.items()
                },
                "new_hashes": {
                    "batch_service": sha256(BATCH_SERVICE),
                    "template": sha256(TEMPLATE),
                    "level_lock": sha256(LOCK),
                    "mn_resolution": sha256(MN_RESOLUTION),
                },
                "special_same_level": sorted(SPECIAL_IDS),
                "code_patches": CODE_PATCHES,
                "preflight": pre,
                "postflight": post,
                "backup": str(backup),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print()
    print("=" * 118)
    print(
        "CÀI ĐẶT THÀNH CÔNG - "
        "MẦM NON ĐÃ PHÂN LOẠI ĐÚNG TRÊN NỀN HIỆN TẠI"
    )
    print("Liên cấp MN: 0")
    print("Đặc thù cùng cấp tách riêng: 3")
    print("  - QD3805-OP-0141: tiếp nhận điểm lẻ MN Diễn Yên")
    print("  - QD3805-OP-0244: tiếp nhận điểm lẻ Long Xá")
    print("  - QD3805-OP-0704: tiếp nhận 6 lớp MN Hermann Gmeiner")
    print("Đã khóa 5 mã trường còn thiếu trong registry nội bộ:")
    for op_id, cfg in CODE_PATCHES.items():
        print(
            f"  - {op_id} / row {cfg['excel_row']}: "
            f"{cfg['code']}"
        )
    print(
        "Action sáp nhập toàn trường MN:",
        post.get("mn_mapped"),
        "/",
        post.get("mn_expected"),
    )
    print(
        "KPI MN:",
        json.dumps(post.get("mn_counts") or {}, ensure_ascii=False),
    )
    print("Candidate MN:", post.get("mn_candidate"))
    print("BLOCK hiệu lực MN:", post.get("mn_effective_block"))
    print(
        "QĐ3805 chưa xác định: 1 "
        "(Mầm non Lượng Minh) - vẫn CHẶN, không tự suy đoán."
    )
    print("Tiểu học: giữ nguyên 160 DONE / 0 READY / 0 BLOCK.")
    print("Database: KHÔNG THAY ĐỔI")
    print("Bộ cài KHÔNG thực hiện sáp nhập.")
    print("Backup:", backup)
    print("Báo cáo:", report)
    print("=" * 118)

except Exception as exc:
    try:
        shutil.copy2(backup_batch, BATCH_SERVICE)
        shutil.copy2(backup_template, TEMPLATE)
        shutil.copy2(backup_lock, LOCK)
        if MN_RESOLUTION.exists():
            MN_RESOLUTION.unlink()
    except Exception:
        pass

    print("=" * 118)
    print("DỪNG AN TOÀN - ĐÃ KHÔI PHỤC CÁC FILE CŨ")
    print("Lỗi:", exc)
    print("Database: KHÔNG CHỦ ĐỘNG GHI")
    print("=" * 118)
    raise SystemExit(1)
