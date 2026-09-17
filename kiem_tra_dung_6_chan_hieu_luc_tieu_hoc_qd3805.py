# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_DIR = Path(__file__).resolve().parent
if not (PROJECT_DIR / "app").exists():
    PROJECT_DIR = Path.cwd()
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from app.database import DATABASE_PATH  # noqa: E402
from app.services import school_merger_service as engine  # noqa: E402
from app.services import school_merger_level_batch_service as batch  # noqa: E402
from app.services.school_merger_source_audit_service import audit_official_plans  # noqa: E402
from app.services.school_merger_preview_service import build_official_plan_impact_preview  # noqa: E402

TARGET_YEAR = "2026-2027"
TARGET_LEVEL = "TH"
OUT_DIR = PROJECT_DIR / "exports" / "Kiem_Tra_Dung_6_Chan_Hieu_Luc_TH_QD3805"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def school_year_id() -> int:
    for y in engine.list_school_years():
        code = str(y.get("code") or y.get("name") or "")
        code = code.replace("–", "-").replace("—", "-")
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


def ro_connect() -> sqlite3.Connection:
    p = Path(DATABASE_PATH).resolve()
    con = sqlite3.connect(p.as_uri() + "?mode=ro", uri=True, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only=ON")
    con.execute("PRAGMA foreign_keys=ON")
    return con


def table_exists(con: sqlite3.Connection, table: str) -> bool:
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (table,),
    ).fetchone() is not None


def contains_exact(obj: Any, wanted: set[int]) -> bool:
    if isinstance(obj, bool) or obj is None:
        return False
    if isinstance(obj, int):
        return obj in wanted
    if isinstance(obj, float) and obj.is_integer():
        return int(obj) in wanted
    if isinstance(obj, str):
        s = obj.strip()
        if s.isdigit():
            return int(s) in wanted
        return False
    if isinstance(obj, dict):
        return any(contains_exact(v, wanted) for v in obj.values())
    if isinstance(obj, list):
        return any(contains_exact(v, wanted) for v in obj)
    return False


def exact_history(con: sqlite3.Connection, school_ids: list[int]) -> list[dict[str, Any]]:
    wanted = {int(x) for x in school_ids if x is not None}
    out = []
    if not wanted:
        return out
    for table in (
        "school_merger_operations",
        "school_merger_official_executions",
        "school_merger_level_batches",
    ):
        if not table_exists(con, table):
            continue
        cols = [r["name"] for r in con.execute(f"PRAGMA table_info({table})").fetchall()]
        rows = con.execute(f"SELECT * FROM {table} ORDER BY id").fetchall()
        for raw in rows:
            row = dict(raw)
            matched_fields = []
            for c in cols:
                v = row.get(c)
                if c.endswith("_school_id") or c == "school_id":
                    try:
                        if int(v) in wanted:
                            matched_fields.append(c)
                    except Exception:
                        pass
                elif c.endswith("_json"):
                    try:
                        parsed = json.loads(str(v or ""))
                    except Exception:
                        continue
                    if contains_exact(parsed, wanted):
                        matched_fields.append(c)
            if matched_fields:
                out.append({
                    "table": table,
                    "id": row.get("id"),
                    "matched_fields": matched_fields,
                    "row": safe(row),
                })
    return out


def extract_failures(obj: Any, path: str = "") -> list[str]:
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{path}.{k}" if path else str(k)
            lk = str(k).lower()
            if isinstance(v, bool) and v is False and any(
                token in lk for token in ("pass", "ok", "valid", "ready", "safe", "match")
            ):
                out.append(f"{p}=False")
            if lk in {"blockers", "errors", "error", "failures", "issues"} and v:
                out.append(f"{p}={json.dumps(safe(v), ensure_ascii=False, default=str)}")
            out.extend(extract_failures(v, p))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out.extend(extract_failures(v, f"{path}[{i}]"))
    return list(dict.fromkeys(out))


def plan_ids_from_preview(preview: dict[str, Any]) -> tuple[list[str], list[dict[str, Any]]]:
    ids = []
    for p in preview.get("rows") or []:
        if str(p.get("batch_state") or "").upper() == "BLOCK":
            pid = str(p.get("id") or "").strip()
            if pid and pid not in ids:
                ids.append(pid)
    extras = [dict(x) for x in (preview.get("extra_blockers") or [])]
    for x in extras:
        pid = str(x.get("plan_id") or "").strip()
        if pid and pid not in ids:
            ids.append(pid)
    return ids, extras


def main() -> None:
    print("=" * 118)
    print("KIỂM TRA ĐÚNG 6 CHẶN HIỆU LỰC - TIỂU HỌC - QĐ3805")
    print("Chế độ: CHỈ ĐỌC / KHÔNG GHI DATABASE / KHÔNG SÁP NHẬP")
    print("Database:", DATABASE_PATH)
    print("=" * 118)

    dbp = Path(DATABASE_PATH)
    before = sha256_file(dbp)
    yid = school_year_id()

    preview = batch.build_level_batch_preview(
        school_year_id=yid,
        level_code=TARGET_LEVEL,
    )
    plan_ids, extras = plan_ids_from_preview(preview)
    rows_by_id = {
        str(x.get("id") or ""): dict(x)
        for x in (preview.get("rows") or [])
    }

    audit = audit_official_plans(
        school_year_id=yid,
        commune_id=None,
        level_code=TARGET_LEVEL,
    )
    audit_map = {
        str((x.get("plan") or {}).get("id") or ""): safe(x.get("audit") or {})
        for x in (audit.get("rows") or [])
    }

    details = []
    with ro_connect() as con:
        for pid in plan_ids:
            p = rows_by_id.get(pid) or {}
            impact = None
            impact_error = None
            try:
                impact = safe(build_official_plan_impact_preview(pid))
            except Exception as exc:
                impact_error = f"{type(exc).__name__}: {exc}"

            source_ids = []
            source_rows = []
            for s in p.get("source_schools") or []:
                try:
                    sid = int((s or {}).get("id"))
                except Exception:
                    continue
                source_ids.append(sid)
                source_rows.append(safe(s))

            try:
                target_id = int((p.get("target_school") or {}).get("id"))
            except Exception:
                target_id = None

            all_ids = source_ids + ([target_id] if target_id is not None else [])
            full_audit = audit_map.get(pid) or {}
            failures = extract_failures(full_audit)

            details.append({
                "plan_id": pid,
                "qd3805_operation_id": str(p.get("qd3805_operation_id") or ""),
                "commune": str(p.get("commune_excel") or p.get("commune_name") or ""),
                "title": str(p.get("plan_text") or ""),
                "batch_state": str(p.get("batch_state") or ""),
                "batch_blockers": safe(p.get("batch_blockers") or []),
                "source_schools": source_rows,
                "target_school": safe(p.get("target_school") or {}),
                "source_audit_full": full_audit,
                "source_audit_failures": failures,
                "impact_preview": impact,
                "impact_preview_error": impact_error,
                "history_exact": exact_history(con, all_ids),
            })

    unresolved = safe((preview.get("registry") or {}).get("unresolved_orphans") or [])

    after = sha256_file(dbp)
    unchanged = before == after

    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "database_unchanged": unchanged,
        "summary": {
            "counts": safe(preview.get("counts") or {}),
            "effective_block_count": int(preview.get("effective_block_count") or 0),
            "base_block_count": int((preview.get("counts") or {}).get("BLOCK") or 0),
            "extra_blocker_count": len(extras),
            "unique_mapped_effective_blockers": len(plan_ids),
            "unresolved_count": len(unresolved),
            "registry_action_mapped_count": int(preview.get("registry_action_mapped_count") or 0),
            "registry_action_expected_count": int(preview.get("registry_action_expected_count") or 0),
        },
        "extra_blockers": safe(extras),
        "mapped_effective_blockers": details,
        "unresolved_qd3805": unresolved,
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    jp = OUT_DIR / f"bao_cao_dung_6_chan_hieu_luc_TH_QD3805_{stamp}.json"
    tp = OUT_DIR / f"tom_tat_dung_6_chan_hieu_luc_TH_QD3805_{stamp}.txt"
    jp.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    lines = [
        "KIỂM TRA ĐÚNG 6 CHẶN HIỆU LỰC - TIỂU HỌC - QĐ3805",
        "=" * 110,
        f"DONE={report['summary']['counts'].get('DONE')} | READY={report['summary']['counts'].get('READY')} | "
        f"BLOCK gốc={report['summary']['base_block_count']} | EXTRA blocker={report['summary']['extra_blocker_count']} | "
        f"BLOCK hiệu lực={report['summary']['effective_block_count']}",
        f"Mapped effective blocker={report['summary']['unique_mapped_effective_blockers']} | "
        f"QĐ3805 chưa xác định={report['summary']['unresolved_count']}",
        "",
    ]

    for d in details:
        lines.append("-" * 110)
        lines.append(
            f"{d['qd3805_operation_id']} | {d['commune']} | {d['title']} | "
            f"plan_id={d['plan_id']} | state={d['batch_state']}"
        )
        if d["batch_blockers"]:
            lines.append("BLOCKERS GỐC:")
            for x in d["batch_blockers"]:
                lines.append("  - " + str(x))
        if d["source_audit_failures"]:
            lines.append("CHI TIẾT FAIL TRONG SOURCE AUDIT:")
            for x in d["source_audit_failures"][:80]:
                lines.append("  * " + x)
        else:
            lines.append("CHI TIẾT FAIL TRONG SOURCE AUDIT: không phát hiện key lỗi rõ trong cấu trúc trả về.")

        imp = d.get("impact_preview") or {}
        if d.get("impact_preview_error"):
            lines.append("IMPACT PREVIEW ERROR: " + d["impact_preview_error"])
        else:
            lines.append(
                "IMPACT: safe={safe} | simulation={sim} | state={state} | source={source}".format(
                    safe=imp.get("safe_for_future_execution"),
                    sim=imp.get("simulation_ok"),
                    state=imp.get("v41_state_check_ok"),
                    source=imp.get("v43_source_check_ok"),
                )
            )
            for x in imp.get("blockers") or []:
                lines.append("  ! " + str(x))

        if d["history_exact"]:
            lines.append("LỊCH SỬ SÁP NHẬP KHỚP SCHOOL_ID CHÍNH XÁC:")
            for h in d["history_exact"]:
                lines.append(
                    f"  - {h.get('table')} id={h.get('id')} | fields={','.join(h.get('matched_fields') or [])}"
                )
        else:
            lines.append("LỊCH SỬ SÁP NHẬP KHỚP SCHOOL_ID CHÍNH XÁC: không tìm thấy.")

    lines.append("")
    lines.append("-" * 110)
    lines.append("QĐ3805 CHƯA XÁC ĐỊNH:")
    for x in unresolved:
        lines.append(
            f"  - STT {x.get('stt')} | {x.get('commune')} | {x.get('school')} | {x.get('status')}"
        )
    lines.append("-" * 110)
    lines.append("Database: " + ("KHÔNG THAY ĐỔI" if unchanged else "CẢNH BÁO HASH THAY ĐỔI"))
    lines.append("JSON: " + str(jp))
    lines.append("TXT: " + str(tp))
    tp.write_text("\n".join(lines), encoding="utf-8")

    s = report["summary"]
    print(
        f"DONE={s['counts'].get('DONE')} | READY={s['counts'].get('READY')} | "
        f"BLOCK gốc={s['base_block_count']} | EXTRA={s['extra_blocker_count']} | "
        f"BLOCK hiệu lực={s['effective_block_count']}"
    )
    print(f"MAPPED EFFECTIVE BLOCKER={s['unique_mapped_effective_blockers']}")
    print(f"QĐ3805 CHƯA XÁC ĐỊNH={s['unresolved_count']}")
    print("-" * 118)
    for d in details:
        print(f"{d['qd3805_operation_id']} | {d['commune']} | {d['title']} | state={d['batch_state']}")
        for x in d["batch_blockers"]:
            print("  -", x)
        for x in d["source_audit_failures"][:20]:
            print("  *", x)
        imp = d.get("impact_preview") or {}
        for x in imp.get("blockers") or []:
            print("  !", x)
        if d["history_exact"]:
            for h in d["history_exact"]:
                print(f"  HISTORY: {h.get('table')} id={h.get('id')} fields={','.join(h.get('matched_fields') or [])}")
    print("-" * 118)
    print("Database:", "KHÔNG THAY ĐỔI" if unchanged else "CẢNH BÁO HASH THAY ĐỔI")
    print("TXT:", tp)
    print("=" * 118)

    if not unchanged:
        raise SystemExit("DỪNG: hash database đã thay đổi ngoài dự kiến.")


if __name__ == "__main__":
    main()
