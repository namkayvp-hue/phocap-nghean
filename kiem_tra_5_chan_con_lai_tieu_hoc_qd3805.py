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
OUT_DIR = PROJECT_DIR / "exports" / "Kiem_Tra_5_Chan_Con_Lai_TH_QD3805"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): safe_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [safe_json(v) for v in value]
    if hasattr(value, "keys"):
        try:
            return {str(k): safe_json(value[k]) for k in value.keys()}
        except Exception:
            pass
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def school_year_id() -> int:
    for y in engine.list_school_years():
        code = str(y.get("code") or y.get("name") or "")
        code = code.replace("–", "-").replace("—", "-")
        if code == TARGET_YEAR:
            return int(y["id"])
    raise RuntimeError(f"Không tìm thấy năm học {TARGET_YEAR}.")


def ro_connect() -> sqlite3.Connection:
    db = Path(DATABASE_PATH).resolve()
    con = sqlite3.connect(db.as_uri() + "?mode=ro", uri=True, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only=ON")
    con.execute("PRAGMA foreign_keys=ON")
    return con


def table_exists(con: sqlite3.Connection, table: str) -> bool:
    row = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (table,),
    ).fetchone()
    return row is not None


def school_row(con: sqlite3.Connection, school_id: int | None) -> dict[str, Any] | None:
    if school_id is None:
        return None
    cols = {r["name"] for r in con.execute("PRAGMA table_info(schools)").fetchall()}
    select = ["s.id", "s.code", "s.name", "s.is_active"]
    if "commune_id" in cols:
        select.append("s.commune_id")
    if table_exists(con, "communes") and "commune_id" in cols:
        select.append("c.name AS commune_name")
        sql = (
            "SELECT " + ",".join(select) +
            " FROM schools s LEFT JOIN communes c ON c.id=s.commune_id WHERE s.id=?"
        )
    else:
        sql = "SELECT " + ",".join(select) + " FROM schools s WHERE s.id=?"
    row = con.execute(sql, (int(school_id),)).fetchone()
    return dict(row) if row else None


def ids_from_plan(plan: dict[str, Any]) -> tuple[list[int], int | None]:
    source_ids = []
    for s in plan.get("source_schools") or []:
        try:
            sid = int((s or {}).get("id"))
        except Exception:
            continue
        if sid not in source_ids:
            source_ids.append(sid)
    try:
        target_id = int((plan.get("target_school") or {}).get("id"))
    except Exception:
        target_id = None
    return source_ids, target_id


def merger_history_for_school_ids(
    con: sqlite3.Connection,
    school_ids: list[int],
) -> list[dict[str, Any]]:
    wanted = {int(x) for x in school_ids if x is not None}
    if not wanted:
        return []

    tables = [
        "school_merger_operations",
        "school_merger_official_executions",
        "school_merger_level_batches",
    ]
    found = []

    for table in tables:
        if not table_exists(con, table):
            continue
        info = [dict(r) for r in con.execute(f"PRAGMA table_info({table})").fetchall()]
        col_names = {x["name"] for x in info}
        rows = con.execute(f"SELECT * FROM {table} ORDER BY id").fetchall()
        for raw in rows:
            row = dict(raw)
            hit = False
            hit_fields = []

            for field in ("target_school_id", "school_id", "source_school_id"):
                if field in col_names:
                    try:
                        val = int(row.get(field))
                    except Exception:
                        val = None
                    if val in wanted:
                        hit = True
                        hit_fields.append(f"{field}={val}")

            for field in ("source_school_ids_json", "summary_json"):
                if field not in col_names:
                    continue
                text = str(row.get(field) or "")
                try:
                    parsed = json.loads(text)
                except Exception:
                    parsed = text
                blob = json.dumps(parsed, ensure_ascii=False, default=str) if not isinstance(parsed, str) else parsed
                for sid in wanted:
                    if str(sid) in blob:
                        hit = True
                        hit_fields.append(f"{field} chứa {sid}")

            if hit:
                found.append({
                    "table": table,
                    "id": row.get("id"),
                    "hit_fields": hit_fields,
                    "row": safe_json(row),
                })
    return found


def generic_merger_tables(con: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = con.execute(
        "SELECT name, sql FROM sqlite_master "
        "WHERE type='table' AND (lower(name) LIKE '%merger%' OR lower(name) LIKE '%sap%') "
        "ORDER BY name"
    ).fetchall()
    out = []
    for r in rows:
        name = str(r["name"])
        cols = [dict(x) for x in con.execute(f"PRAGMA table_info({name})").fetchall()]
        try:
            count = int(con.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0])
        except Exception:
            count = None
        out.append({
            "name": name,
            "row_count": count,
            "columns": [x.get("name") for x in cols],
        })
    return out


def main() -> None:
    print("=" * 116)
    print("KIỂM TRA 5 CHẶN CÒN LẠI - TIỂU HỌC - QĐ3805")
    print("Dự án:", PROJECT_DIR)
    print("Database:", DATABASE_PATH)
    print("Chế độ: CHỈ ĐỌC / KHÔNG SỬA MÃ NGUỒN / KHÔNG GHI DATABASE / KHÔNG SÁP NHẬP")
    print("=" * 116)

    db_path = Path(DATABASE_PATH)
    db_before = sha256_file(db_path)
    yid = school_year_id()

    preview = batch.build_level_batch_preview(
        school_year_id=yid,
        level_code=TARGET_LEVEL,
    )

    audit = audit_official_plans(
        school_year_id=yid,
        commune_id=None,
        level_code=TARGET_LEVEL,
    )
    audit_map = {
        str((x.get("plan") or {}).get("id") or ""): safe_json(x.get("audit") or {})
        for x in (audit.get("rows") or [])
    }

    # Mapped pure-level blockers only. Undefined QD3805 row is reported separately.
    mapped_blockers = []
    for p in preview.get("rows") or []:
        if str(p.get("batch_state") or "").upper() != "BLOCK":
            continue
        if not str(p.get("qd3805_operation_id") or "").strip():
            continue
        mapped_blockers.append(dict(p))

    # De-duplicate by QD3805 operation id.
    unique = {}
    for p in mapped_blockers:
        unique[str(p.get("qd3805_operation_id"))] = p
    mapped_blockers = list(unique.values())

    details = []
    with ro_connect() as con:
        merger_tables = generic_merger_tables(con)

        for p in mapped_blockers:
            pid = str(p.get("id") or "")
            op_id = str(p.get("qd3805_operation_id") or "")
            source_ids, target_id = ids_from_plan(p)
            all_ids = list(source_ids) + ([target_id] if target_id is not None else [])

            impact = None
            impact_error = None
            try:
                impact = safe_json(build_official_plan_impact_preview(pid))
            except Exception as exc:
                impact_error = f"{type(exc).__name__}: {exc}"

            sources = [school_row(con, sid) for sid in source_ids]
            target = school_row(con, target_id)
            history = merger_history_for_school_ids(con, all_ids)

            details.append({
                "plan_id": pid,
                "qd3805_operation_id": op_id,
                "commune": str(p.get("commune_excel") or p.get("commune_name") or ""),
                "title": str(p.get("plan_text") or ""),
                "match_status": str(p.get("match_status") or ""),
                "match_label": str(p.get("match_label") or ""),
                "action_type": str(p.get("action_type") or ""),
                "execution_status": str(p.get("execution_status") or ""),
                "batch_blockers": safe_json(p.get("batch_blockers") or []),
                "source_audit_from_batch": safe_json(p.get("source_audit") or {}),
                "source_audit_full": audit_map.get(pid),
                "source_schools": safe_json(sources),
                "target_school": safe_json(target),
                "impact_preview": impact,
                "impact_preview_error": impact_error,
                "merger_history_refs": history,
            })

    unresolved = safe_json((preview.get("registry") or {}).get("unresolved_orphans") or [])

    db_after = sha256_file(db_path)
    unchanged = db_before == db_after

    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "database": str(db_path),
        "database_sha256_before": db_before,
        "database_sha256_after": db_after,
        "database_unchanged": unchanged,
        "school_year": TARGET_YEAR,
        "level_code": TARGET_LEVEL,
        "summary": {
            "done": int((preview.get("counts") or {}).get("DONE") or 0),
            "ready": int((preview.get("counts") or {}).get("READY") or 0),
            "base_block": int((preview.get("counts") or {}).get("BLOCK") or 0),
            "effective_block_count": int(preview.get("effective_block_count") or 0),
            "mapped_action_count": int(preview.get("registry_action_mapped_count") or 0),
            "expected_action_count": int(preview.get("registry_action_expected_count") or 0),
            "mapped_blocker_operations": len(mapped_blockers),
            "unresolved_qd3805_rows": len(unresolved),
        },
        "mapped_blockers": details,
        "unresolved_qd3805": unresolved,
        "merger_tables": merger_tables,
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = OUT_DIR / f"bao_cao_5_chan_con_lai_TH_QD3805_{stamp}.json"
    txt_path = OUT_DIR / f"tom_tat_5_chan_con_lai_TH_QD3805_{stamp}.txt"

    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )

    lines = []
    lines.append("KIỂM TRA 5 CHẶN CÒN LẠI - TIỂU HỌC - QĐ3805")
    lines.append("=" * 108)
    s = report["summary"]
    lines.append(
        f"KPI: DONE={s['done']} | READY={s['ready']} | "
        f"BLOCK gốc={s['base_block']} | BLOCK hiệu lực={s['effective_block_count']}"
    )
    lines.append(
        f"QĐ3805 mapped={s['mapped_action_count']}/{s['expected_action_count']} | "
        f"mapped blockers={s['mapped_blocker_operations']} | "
        f"unresolved official rows={s['unresolved_qd3805_rows']}"
    )
    lines.append("")

    for d in details:
        lines.append("-" * 108)
        lines.append(
            f"{d['qd3805_operation_id']} | {d['commune']} | {d['title']} | plan_id={d['plan_id']}"
        )
        lines.append("Blockers hiện tại:")
        for x in d["batch_blockers"] or []:
            lines.append("  - " + str(x))

        lines.append("Nguồn:")
        for x in d["source_schools"] or []:
            if not x:
                continue
            lines.append(
                "  - school_id={id} | mã={code} | {name} | active={is_active} | {commune}".format(
                    id=x.get("id"),
                    code=x.get("code"),
                    name=x.get("name"),
                    is_active=x.get("is_active"),
                    commune=x.get("commune_name") or "",
                )
            )
        t = d["target_school"] or {}
        if t:
            lines.append(
                "Đích: school_id={id} | mã={code} | {name} | active={is_active} | {commune}".format(
                    id=t.get("id"),
                    code=t.get("code"),
                    name=t.get("name"),
                    is_active=t.get("is_active"),
                    commune=t.get("commune_name") or "",
                )
            )
        else:
            lines.append("Đích: CHƯA XÁC ĐỊNH")

        audit_full = d.get("source_audit_full") or {}
        if audit_full:
            lines.append(f"Source audit pass={audit_full.get('pass')}")
            for x in audit_full.get("blockers") or []:
                lines.append("  * " + str(x))
            # Print common detail fields without assuming exact schema.
            for key in (
                "errors", "warnings", "checks", "source_checks",
                "duplicate_people", "residuals", "summary",
            ):
                value = audit_full.get(key)
                if value:
                    lines.append(f"{key}: {json.dumps(value, ensure_ascii=False, default=str)}")

        if d.get("impact_preview_error"):
            lines.append("Impact preview lỗi: " + d["impact_preview_error"])
        else:
            impact = d.get("impact_preview") or {}
            lines.append(
                "Impact: safe={safe} | simulation_ok={sim} | state_ok={state} | source_ok={src}".format(
                    safe=impact.get("safe_for_future_execution"),
                    sim=impact.get("simulation_ok"),
                    state=impact.get("v41_state_check_ok"),
                    src=impact.get("v43_source_check_ok"),
                )
            )
            for x in impact.get("blockers") or []:
                lines.append("  ! " + str(x))

        if d.get("merger_history_refs"):
            lines.append("Lịch sử sáp nhập có liên quan:")
            for h in d["merger_history_refs"]:
                lines.append(
                    f"  - {h.get('table')} id={h.get('id')} | "
                    + "; ".join(h.get("hit_fields") or [])
                )
        else:
            lines.append("Lịch sử sáp nhập có liên quan: không tìm thấy trong các bảng nhật ký chuẩn.")

    lines.append("")
    lines.append("-" * 108)
    lines.append("QĐ3805 CHƯA XÁC ĐỊNH / NGOÀI 5 MAPPED BLOCKER:")
    for x in unresolved:
        lines.append(
            f"  - STT {x.get('stt')} | {x.get('commune')} | {x.get('school')} | {x.get('status')}"
        )
    lines.append("-" * 108)
    lines.append("Database: " + ("KHÔNG THAY ĐỔI" if unchanged else "CẢNH BÁO HASH ĐÃ THAY ĐỔI"))
    lines.append("Báo cáo JSON: " + str(json_path))
    lines.append("Tóm tắt TXT: " + str(txt_path))

    txt_path.write_text("\n".join(lines), encoding="utf-8")

    print(f"DONE: {s['done']}")
    print(f"READY: {s['ready']}")
    print(f"BLOCK hiệu lực: {s['effective_block_count']}")
    print(f"MAPPED BLOCKER OPERATION: {s['mapped_blocker_operations']}")
    print(f"QĐ3805 CHƯA XÁC ĐỊNH: {s['unresolved_qd3805_rows']}")
    print("-" * 116)
    for d in details:
        print(f"{d['qd3805_operation_id']} | {d['commune']} | {d['title']}")
        for x in d["batch_blockers"] or []:
            print("  -", x)
    print("-" * 116)
    print("Database:", "KHÔNG THAY ĐỔI" if unchanged else "CẢNH BÁO HASH THAY ĐỔI")
    print("Báo cáo JSON:", json_path)
    print("Tóm tắt TXT:", txt_path)
    print("=" * 116)

    if not unchanged:
        raise SystemExit("DỪNG: hash database thay đổi ngoài dự kiến.")


if __name__ == "__main__":
    main()
