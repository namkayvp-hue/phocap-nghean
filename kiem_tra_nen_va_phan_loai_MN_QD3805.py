# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(r"C:\PhoCap")
DB = ROOT / "data" / "phocap.db"
OUT_DIR = ROOT / "exports" / "Kiem_Tra_Nen_Mam_Non_QD3805"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services import school_merger_service as engine  # noqa: E402
from app.services.school_merger_level_batch_service import build_level_batch_preview  # noqa: E402

TARGET_YEAR = "2026-2027"
TARGET_LEVEL = "MN"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def ro_connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB.resolve().as_uri() + "?mode=ro", uri=True, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only=ON")
    con.execute("PRAGMA foreign_keys=ON")
    return con


def school_year_id() -> int:
    for y in engine.list_school_years():
        code = str(y.get("code") or y.get("name") or "").replace("–", "-").replace("—", "-")
        if code == TARGET_YEAR:
            return int(y["id"])
    raise RuntimeError(f"Không tìm thấy năm học {TARGET_YEAR}.")


def safe(v: Any) -> Any:
    if isinstance(v, dict):
        return {str(k): safe(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [safe(x) for x in v]
    if hasattr(v, "keys"):
        try:
            return {str(k): safe(v[k]) for k in v.keys()}
        except Exception:
            pass
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v
    return str(v)


def reason_groups(row: dict[str, Any]) -> list[str]:
    text = " | ".join(str(x) for x in (row.get("batch_blockers") or [])).upper()
    out = []

    if any(k in text for k in (
        "KHỚP TÊN", "CHƯA KHỚP", "MATCH", "TRƯỜNG DB", "NGUỒN/ĐÍCH",
        "SCHOOL_ID", "KHÔNG XÁC ĐỊNH ĐƯỢC TRƯỜNG",
    )):
        out.append("KHOP_TRUONG_DB")

    if any(k in text for k in (
        "KIỂM TRA DỮ LIỆU NGUỒN", "KIỂM TRA NGUỒN", "SOURCE", "V4.3",
        "NHÂN SỰ", "ĐỘI NGŨ",
    )):
        out.append("KIEM_TRA_NGUON")

    if any(k in text for k in ("ĐANG BỊ KHÓA", "INACTIVE", "KHÔNG HOẠT ĐỘNG")):
        out.append("NGUON_INACTIVE")

    if any(k in text for k in ("MÔ PHỎNG", "XEM TRƯỚC", "PREVIEW", "SIMULATION")):
        out.append("XEM_TRUOC_MO_PHONG")

    if any(k in text for k in ("TRÙNG", "DUPLICATE", "CHỒNG LẤN")):
        out.append("TRUNG_LAP_CHONG_LAN")

    if not out:
        out.append("KHAC")
    return out


def main() -> None:
    print("=" * 118)
    print("BẮT ĐẦU CẤP MẦM NON - KIỂM TRA NỀN VÀ PHÂN LOẠI QĐ3805")
    print("Dự án:", ROOT)
    print("Database:", DB)
    print("Chế độ: CHỈ ĐỌC - KHÔNG SỬA MÃ NGUỒN - KHÔNG GHI DATABASE - KHÔNG SÁP NHẬP")
    print("=" * 118)

    if not DB.exists():
        raise SystemExit("Không tìm thấy C:\\PhoCap\\data\\phocap.db")

    before = sha256_file(DB)
    yid = school_year_id()

    with ro_connect() as con:
        integrity = str(con.execute("PRAGMA integrity_check").fetchone()[0])
        fk = con.execute("PRAGMA foreign_key_check").fetchall()

        mn_batch_count = 0
        th_batch_count = 0
        table = con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='school_merger_level_batches'"
        ).fetchone()
        if table is not None:
            mn_batch_count = int(con.execute(
                "SELECT COUNT(*) FROM school_merger_level_batches "
                "WHERE school_year_id=? AND level_code='MN'",
                (yid,),
            ).fetchone()[0])
            th_batch_count = int(con.execute(
                "SELECT COUNT(*) FROM school_merger_level_batches "
                "WHERE school_year_id=? AND level_code='TH'",
                (yid,),
            ).fetchone()[0])

    preview = build_level_batch_preview(
        school_year_id=yid,
        level_code=TARGET_LEVEL,
    )

    counts = dict(preview.get("counts") or {})
    rows = [dict(x) for x in (preview.get("rows") or [])]
    blockers = [
        x for x in rows
        if str(x.get("batch_state") or "").upper() == "BLOCK"
    ]

    by_reason = Counter()
    blocker_details = []
    seen = set()
    for row in blockers:
        op_id = str(row.get("qd3805_operation_id") or row.get("id") or "").strip()
        if op_id in seen:
            continue
        seen.add(op_id)
        groups = reason_groups(row)
        for g in groups:
            by_reason[g] += 1
        blocker_details.append({
            "operation_id": op_id,
            "commune": str(row.get("commune_excel") or row.get("commune_name") or ""),
            "plan_text": str(row.get("plan_text") or ""),
            "match_status": str(row.get("match_status") or ""),
            "match_label": str(row.get("match_label") or ""),
            "groups": groups,
            "blockers": safe(row.get("batch_blockers") or []),
            "source_schools": safe(row.get("source_schools") or []),
            "target_school": safe(row.get("target_school") or {}),
        })

    extras = [dict(x) for x in (preview.get("extra_blockers") or [])]
    unresolved = safe((preview.get("registry") or {}).get("unresolved_orphans") or [])

    after = sha256_file(DB)
    unchanged = before == after

    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "database": str(DB),
        "database_unchanged": unchanged,
        "integrity": integrity,
        "foreign_key_errors": len(fk),
        "school_year": TARGET_YEAR,
        "level_code": TARGET_LEVEL,
        "existing_batches": {
            "MN": mn_batch_count,
            "TH": th_batch_count,
        },
        "summary": {
            "counts": counts,
            "registry_action_expected_count": int(preview.get("registry_action_expected_count") or 0),
            "registry_action_mapped_count": int(preview.get("registry_action_mapped_count") or 0),
            "registry_keep_expected_count": int(preview.get("registry_keep_expected_count") or 0),
            "registry_unresolved_count": int(preview.get("registry_unresolved_count") or 0),
            "registry_deferred_unresolved_count": int(preview.get("registry_deferred_unresolved_count") or 0),
            "excluded_cross_level_count": int(preview.get("excluded_cross_level_count") or 0),
            "effective_block_count": int(preview.get("effective_block_count") or 0),
            "candidate_count": int(preview.get("candidate_count") or 0),
            "ready_for_execution": bool(preview.get("ready_for_execution")),
            "all_done": bool(preview.get("all_done")),
            "previous_batch": bool(preview.get("previous_batch")),
            "unique_base_blockers": len(blocker_details),
            "extra_blockers": len(extras),
        },
        "blocker_groups": dict(sorted(by_reason.items())),
        "blockers": blocker_details,
        "extra_blockers": safe(extras),
        "unresolved_qd3805": unresolved,
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    jp = OUT_DIR / f"kiem_tra_nen_MN_QD3805_{stamp}.json"
    tp = OUT_DIR / f"tom_tat_nen_MN_QD3805_{stamp}.txt"
    jp.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    s = report["summary"]
    lines = [
        "BẮT ĐẦU CẤP MẦM NON - KIỂM TRA NỀN VÀ PHÂN LOẠI QĐ3805",
        "=" * 112,
        f"Integrity: {integrity}",
        f"Foreign key errors: {len(fk)}",
        f"Batch MN đã có: {mn_batch_count}",
        f"Batch TH đã có: {th_batch_count}",
        "",
        "KPI MẦM NON:",
        f"  KEEP: {counts.get('KEEP', 0)}",
        f"  DONE: {counts.get('DONE', 0)}",
        f"  READY: {counts.get('READY', 0)}",
        f"  BLOCK: {counts.get('BLOCK', 0)}",
        "",
        f"QĐ3805 action expected: {s['registry_action_expected_count']}",
        f"QĐ3805 mapped: {s['registry_action_mapped_count']}",
        f"QĐ3805 keep expected: {s['registry_keep_expected_count']}",
        f"Liên cấp/đặc thù tách riêng: {s['excluded_cross_level_count']}",
        f"QĐ3805 chưa xác định: {s['registry_unresolved_count']}",
        f"BLOCK hiệu lực: {s['effective_block_count']}",
        f"Candidate READY: {s['candidate_count']}",
        f"Ready for execution: {s['ready_for_execution']}",
        "",
        "PHÂN NHÓM BLOCK GỐC:",
    ]
    if by_reason:
        for k, v in sorted(by_reason.items(), key=lambda x: (-x[1], x[0])):
            lines.append(f"  {k}: {v}")
    else:
        lines.append("  Không có BLOCK gốc.")

    lines.append("")
    lines.append("CHI TIẾT BLOCK:")
    for d in blocker_details:
        lines.append("-" * 112)
        lines.append(
            f"{d['operation_id']} | {d['commune']} | {d['plan_text']} | "
            f"{','.join(d['groups'])}"
        )
        for x in d["blockers"]:
            lines.append("  - " + str(x))

    if extras:
        lines.append("")
        lines.append("EXTRA BLOCKERS:")
        for x in extras:
            lines.append("  - " + json.dumps(safe(x), ensure_ascii=False, default=str))

    if unresolved:
        lines.append("")
        lines.append("QĐ3805 CHƯA XÁC ĐỊNH:")
        for x in unresolved:
            lines.append("  - " + json.dumps(x, ensure_ascii=False, default=str))

    lines.append("")
    lines.append("Database: " + ("KHÔNG THAY ĐỔI" if unchanged else "CẢNH BÁO HASH THAY ĐỔI"))
    lines.append("JSON: " + str(jp))
    lines.append("TXT: " + str(tp))
    tp.write_text("\n".join(lines), encoding="utf-8")

    print("KPI MẦM NON:")
    print(
        f"  KEEP={counts.get('KEEP',0)} | DONE={counts.get('DONE',0)} | "
        f"READY={counts.get('READY',0)} | BLOCK={counts.get('BLOCK',0)}"
    )
    print(
        f"  QĐ3805 action={s['registry_action_mapped_count']}/{s['registry_action_expected_count']} | "
        f"keep={s['registry_keep_expected_count']} | "
        f"đặc thù={s['excluded_cross_level_count']} | "
        f"chưa xác định={s['registry_unresolved_count']}"
    )
    print(
        f"  BLOCK hiệu lực={s['effective_block_count']} | "
        f"candidate={s['candidate_count']} | "
        f"ready={s['ready_for_execution']}"
    )
    print("-" * 118)
    print("PHÂN NHÓM BLOCK:")
    if by_reason:
        for k, v in sorted(by_reason.items(), key=lambda x: (-x[1], x[0])):
            print(f"  {k}: {v}")
    else:
        print("  Không có BLOCK gốc.")
    print("-" * 118)
    print("Database:", "KHÔNG THAY ĐỔI" if unchanged else "CẢNH BÁO HASH THAY ĐỔI")
    print("TXT:", tp)
    print("=" * 118)

    if integrity.lower() != "ok" or fk:
        raise SystemExit("DỪNG: database không đạt integrity/FK.")
    if not unchanged:
        raise SystemExit("DỪNG: hash database thay đổi ngoài dự kiến.")
    if mn_batch_count:
        raise SystemExit("DỪNG: đã tồn tại batch MN; không được chuẩn bị chạy lại.")


if __name__ == "__main__":
    main()
