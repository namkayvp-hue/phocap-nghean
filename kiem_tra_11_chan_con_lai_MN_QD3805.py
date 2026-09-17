# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import sys
import unicodedata
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(r"C:\PhoCap")
DB = ROOT / "data" / "phocap.db"
LOCK = ROOT / "data" / "school_merger_registry" / "qd3805_level_lock.json"
OUT_DIR = ROOT / "exports" / "Kiem_Tra_11_Chan_Mam_Non_QD3805"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services import school_merger_service as engine  # noqa: E402
from app.services.school_merger_level_batch_service import build_level_batch_preview  # noqa: E402
from app.services.school_merger_source_audit_service import audit_official_plans  # noqa: E402

TARGET_YEAR = "2026-2027"
TARGET_LEVEL = "MN"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def norm(v: Any) -> str:
    s = str(v or "").strip().lower().replace("đ", "d")
    s = "".join(
        ch for ch in unicodedata.normalize("NFD", s)
        if unicodedata.category(ch) != "Mn"
    )
    s = re.sub(r"[^a-z0-9]+", " ", s)
    s = re.sub(r"\btruong\b", " ", s)
    return " ".join(s.split())


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


def school_year_id() -> int:
    for y in engine.list_school_years():
        code = str(y.get("code") or y.get("name") or "").replace("–", "-").replace("—", "-")
        if code == TARGET_YEAR:
            return int(y["id"])
    raise RuntimeError(f"Không tìm thấy năm học {TARGET_YEAR}.")


def ro_connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB.resolve().as_uri() + "?mode=ro", uri=True, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only=ON")
    con.execute("PRAGMA foreign_keys=ON")
    return con


def load_lock() -> dict[str, Any]:
    if not LOCK.exists():
        raise RuntimeError("Không tìm thấy qd3805_level_lock.json.")
    return json.loads(LOCK.read_text(encoding="utf-8"))


def blocker_groups(row: dict[str, Any], audit: dict[str, Any]) -> list[str]:
    text = " | ".join(str(x) for x in (row.get("batch_blockers") or [])).upper()
    out = []

    if (
        str(row.get("match_status") or "").upper() != "MATCHED"
        or "KHỚP" in text
        or "TRƯỜNG DB" in text
        or "NGUỒN/ĐÍCH" in text
        or "KHÔNG XÁC ĐỊNH" in text
    ):
        out.append("KHOP_TRUONG_DB")

    if not bool(audit.get("pass")):
        out.append("KIEM_TRA_NGUON")

    if any(k in text for k in ("INACTIVE", "ĐANG BỊ KHÓA", "KHÔNG HOẠT ĐỘNG")):
        out.append("NGUON_INACTIVE")

    if any(k in text for k in ("PREVIEW", "MÔ PHỎNG", "XEM TRƯỚC", "SIMULATION")):
        out.append("XEM_TRUOC_MO_PHONG")

    if not out:
        out.append("KHAC")
    return out


def extract_audit_failures(audit: dict[str, Any]) -> list[str]:
    out: list[str] = []

    for x in audit.get("blockers") or []:
        out.append(str(x))

    for sc in audit.get("school_checks") or []:
        if not isinstance(sc, dict):
            continue
        school_name = str(sc.get("school_name") or sc.get("name") or "")
        role = str(sc.get("role") or "")
        if sc.get("pass") is False:
            out.append(f"{role} {school_name}: pass=False")
        for key in ("blockers", "errors", "issues"):
            val = sc.get(key)
            if val:
                out.append(
                    f"{role} {school_name} {key}: "
                    + json.dumps(safe(val), ensure_ascii=False, default=str)
                )

    return list(dict.fromkeys(out))


def db_school_by_code(con: sqlite3.Connection, code: str) -> list[dict[str, Any]]:
    rows = con.execute(
        "SELECT s.id,s.code,s.name,s.is_active,c.name AS commune_name "
        "FROM schools s LEFT JOIN communes c ON c.id=s.commune_id "
        "WHERE s.code=? ORDER BY s.id",
        (code,),
    ).fetchall()
    return [dict(r) for r in rows]


def main() -> None:
    print("=" * 118)
    print("KIỂM TRA 11 CHẶN CÒN LẠI - MẦM NON - QĐ3805")
    print("Chế độ: CHỈ ĐỌC / KHÔNG SỬA SOURCE / KHÔNG GHI DATABASE / KHÔNG SÁP NHẬP")
    print("Database:", DB)
    print("=" * 118)

    before = sha256_file(DB)
    yid = school_year_id()

    preview = build_level_batch_preview(
        school_year_id=yid,
        level_code=TARGET_LEVEL,
    )
    counts = dict(preview.get("counts") or {})

    audit = audit_official_plans(
        school_year_id=yid,
        commune_id=None,
        level_code=TARGET_LEVEL,
    )
    audit_map = {
        str((x.get("plan") or {}).get("id") or ""): safe(x.get("audit") or {})
        for x in (audit.get("rows") or [])
    }

    lock_payload = load_lock()
    lock_by_op = {
        str(x.get("operation_id") or ""): dict(x)
        for x in (lock_payload.get("operations") or [])
        if isinstance(x, dict)
    }

    rows = []
    seen = set()

    with ro_connect() as con:
        for p in preview.get("rows") or []:
            if str(p.get("batch_state") or "").upper() != "BLOCK":
                continue

            op_id = str(p.get("qd3805_operation_id") or "").strip()
            if not op_id or op_id in seen:
                continue
            seen.add(op_id)

            pid = str(p.get("id") or "")
            audit_item = audit_map.get(pid) or {}
            lock_op = lock_by_op.get(op_id) or {}

            lock_sources = []
            missing_lock_codes = 0

            for s in lock_op.get("source_schools") or []:
                if not isinstance(s, dict):
                    continue
                codes = [
                    str(x or "").strip()
                    for x in (s.get("codes") or [])
                    if str(x or "").strip()
                ]
                if not codes:
                    missing_lock_codes += 1

                db_matches = []
                for code in codes:
                    db_matches.extend(db_school_by_code(con, code))

                lock_sources.append({
                    "excel_row": s.get("excel_row"),
                    "stt": s.get("stt"),
                    "name": str(s.get("name") or ""),
                    "codes": codes,
                    "levels": safe(s.get("levels") or []),
                    "db_matches": safe(db_matches),
                })

            target_codes = [
                str(x or "").strip()
                for x in (lock_op.get("target_codes") or [])
                if str(x or "").strip()
            ]
            target_db_matches = []
            for code in target_codes:
                target_db_matches.extend(db_school_by_code(con, code))

            groups = blocker_groups(dict(p), audit_item)
            failures = extract_audit_failures(audit_item)

            rows.append({
                "operation_id": op_id,
                "plan_id": pid,
                "commune": str(p.get("commune_excel") or p.get("commune_name") or ""),
                "plan_text": str(p.get("plan_text") or ""),
                "batch_blockers": safe(p.get("batch_blockers") or []),
                "match_status": str(p.get("match_status") or ""),
                "match_label": str(p.get("match_label") or ""),
                "groups": groups,
                "source_audit_pass": bool(audit_item.get("pass")),
                "source_audit_failures": failures,
                "source_audit_full": audit_item,
                "current_source_schools": safe(p.get("source_schools") or []),
                "current_target_school": safe(p.get("target_school") or {}),
                "lock_source_schools": lock_sources,
                "lock_target_text": str(lock_op.get("target_text") or ""),
                "lock_target_codes": target_codes,
                "lock_target_db_matches": safe(target_db_matches),
                "missing_lock_source_codes": missing_lock_codes,
            })

    group_counts = Counter()
    for r in rows:
        for g in r["groups"]:
            group_counts[g] += 1

    unresolved = safe((preview.get("registry") or {}).get("unresolved_orphans") or [])
    extras = safe(preview.get("extra_blockers") or [])

    after = sha256_file(DB)
    unchanged = before == after

    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "database_unchanged": unchanged,
        "summary": {
            "counts": counts,
            "expected_actions": int(preview.get("registry_action_expected_count") or 0),
            "mapped_actions": int(preview.get("registry_action_mapped_count") or 0),
            "keep_expected": int(preview.get("registry_keep_expected_count") or 0),
            "excluded_cross_level": int(preview.get("excluded_cross_level_count") or 0),
            "base_blockers": len(rows),
            "effective_block_count": int(preview.get("effective_block_count") or 0),
            "unresolved_count": len(unresolved),
            "candidate_count": int(preview.get("candidate_count") or 0),
        },
        "group_counts": dict(sorted(group_counts.items())),
        "rows": rows,
        "extra_blockers": extras,
        "unresolved_qd3805": unresolved,
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    jp = OUT_DIR / f"bao_cao_11_chan_MN_QD3805_{stamp}.json"
    tp = OUT_DIR / f"tom_tat_11_chan_MN_QD3805_{stamp}.txt"

    jp.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )

    lines = [
        "KIỂM TRA 11 CHẶN CÒN LẠI - MẦM NON - QĐ3805",
        "=" * 112,
        f"KEEP={counts.get('KEEP',0)} | DONE={counts.get('DONE',0)} | "
        f"READY={counts.get('READY',0)} | BLOCK={counts.get('BLOCK',0)}",
        f"QĐ3805 action={report['summary']['mapped_actions']}/{report['summary']['expected_actions']} | "
        f"KEEP expected={report['summary']['keep_expected']} | "
        f"liên cấp={report['summary']['excluded_cross_level']} | "
        f"BLOCK hiệu lực={report['summary']['effective_block_count']} | "
        f"chưa xác định={report['summary']['unresolved_count']}",
        "",
        "PHÂN NHÓM 11 BLOCK:",
    ]

    for k, v in sorted(group_counts.items(), key=lambda x: (-x[1], x[0])):
        lines.append(f"  {k}: {v}")

    for r in rows:
        lines.append("")
        lines.append("-" * 112)
        lines.append(
            f"{r['operation_id']} | {r['commune']} | {r['plan_text']} | "
            f"{','.join(r['groups'])}"
        )
        lines.append(
            f"Match: {r['match_status']} | {r['match_label']} | "
            f"source_audit_pass={r['source_audit_pass']}"
        )
        for x in r["batch_blockers"]:
            lines.append("  BLOCK: " + str(x))

        lines.append(
            f"QĐ3805 lock: missing source code={r['missing_lock_source_codes']} | "
            f"target={r['lock_target_text']} | target_codes={','.join(r['lock_target_codes'])}"
        )
        for s in r["lock_source_schools"]:
            dbs = s["db_matches"]
            if dbs:
                db_text = " ; ".join(
                    f"school_id={x.get('id')} mã={x.get('code')} "
                    f"{x.get('name')} active={x.get('is_active')} xã={x.get('commune_name')}"
                    for x in dbs
                )
            else:
                db_text = "KHÔNG TÌM THẤY DB THEO MÃ"
            lines.append(
                f"  QĐ nguồn row {s.get('excel_row')}: {s.get('name')} | "
                f"mã={','.join(s.get('codes') or []) or '(thiếu)'} -> {db_text}"
            )

        if r["source_audit_failures"]:
            lines.append("SOURCE AUDIT FAIL:")
            for x in r["source_audit_failures"]:
                lines.append("  * " + x)

    lines.append("")
    lines.append("-" * 112)
    lines.append("QĐ3805 CHƯA XÁC ĐỊNH:")
    for x in unresolved:
        lines.append("  - " + json.dumps(x, ensure_ascii=False, default=str))

    lines.append("-" * 112)
    lines.append("Database: " + ("KHÔNG THAY ĐỔI" if unchanged else "CẢNH BÁO HASH THAY ĐỔI"))
    lines.append("JSON: " + str(jp))
    lines.append("TXT: " + str(tp))
    tp.write_text("\n".join(lines), encoding="utf-8")

    print(
        f"KEEP={counts.get('KEEP',0)} | DONE={counts.get('DONE',0)} | "
        f"READY={counts.get('READY',0)} | BLOCK={counts.get('BLOCK',0)}"
    )
    print(
        f"BLOCK hiệu lực={report['summary']['effective_block_count']} | "
        f"QĐ3805 chưa xác định={report['summary']['unresolved_count']}"
    )
    print("-" * 118)
    print("PHÂN NHÓM 11 BLOCK:")
    for k, v in sorted(group_counts.items(), key=lambda x: (-x[1], x[0])):
        print(f"  {k}: {v}")
    print("-" * 118)
    for r in rows:
        print(
            f"{r['operation_id']} | {r['commune']} | {r['plan_text']} | "
            f"{','.join(r['groups'])} | "
            f"thiếu mã nguồn QĐ={r['missing_lock_source_codes']}"
        )
    print("-" * 118)
    print("Database:", "KHÔNG THAY ĐỔI" if unchanged else "CẢNH BÁO HASH THAY ĐỔI")
    print("TXT:", tp)
    print("=" * 118)

    if not unchanged:
        raise SystemExit("DỪNG: hash database thay đổi ngoài dự kiến.")


if __name__ == "__main__":
    main()
