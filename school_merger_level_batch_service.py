from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any

from app.services import school_merger_service as engine
from app.services.school_merger_execution_service import annotate_official_plan_execution_status
from app.services.school_merger_official_registry import list_official_registry_plans
from app.services.school_merger_preview_service import (
    SchoolMergerPreviewError,
    _database_state_fingerprint as _preview_database_state_fingerprint,
    build_official_plan_impact_preview,
)
from app.services.school_merger_source_audit_service import audit_official_plans


LEVEL_BATCH_CONFIRM_PHRASE = "SAP NHAP TOAN CAP"
PROJECT_DIR = Path(__file__).resolve().parent.parent.parent
EXPORT_DIR = PROJECT_DIR / "exports"
BATCH_TABLE = "school_merger_level_batches"
OFFICIAL_EXECUTION_TABLE = "school_merger_official_executions"
ALLOWED_LEVELS = {"MN", "TH", "THCS"}
LEVEL_LOCK_PATH = PROJECT_DIR / "data" / "school_merger_registry" / "qd3805_level_lock.json"
LEVEL_LOCK_SCHEMA = "QD3805_LEVEL_LOCK_2026"
LEVEL_LOCK_EFFECTIVE_YEAR = "2026-2027"
TH_RESOLUTION_PATH = PROJECT_DIR / "data" / "school_merger_registry" / "qd3805_th_resolution.json"
MN_RESOLUTION_PATH = PROJECT_DIR / "data" / "school_merger_registry" / "qd3805_mn_resolution.json"


class SchoolMergerLevelBatchError(RuntimeError):
    pass


def _safe_int(value: Any) -> int | None:
    try:
        text = str(value or "").strip()
        return int(text) if text else None
    except (TypeError, ValueError):
        return None


def _level(value: Any) -> str:
    level = str(value or "").strip().upper()
    if level not in ALLOWED_LEVELS:
        raise SchoolMergerLevelBatchError("Cấp học không hợp lệ cho sáp nhập toàn cấp.")
    return level


def _json_hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _safe_folder_piece(value: Any) -> str:
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or "").strip())
    return text.strip("._-")[:70] or "batch"


def _year_info(school_year_id: int) -> dict[str, Any]:
    years = engine.list_school_years()
    row = next((dict(x) for x in years if int(x.get("id") or -1) == int(school_year_id)), None)
    if row is None:
        raise SchoolMergerLevelBatchError("Không tìm thấy năm học đã chọn.")
    return row


def _source_ids_from_plan(plan: dict[str, Any]) -> list[int]:
    out: list[int] = []
    for item in plan.get("source_schools") or []:
        sid = _safe_int((item or {}).get("id"))
        if sid is not None and sid not in out:
            out.append(sid)
    return sorted(out)


def _existing_batch(school_year_id: int, level_code: str) -> dict[str, Any] | None:
    try:
        con = engine._connect(read_only=True)
    except Exception:
        return None
    try:
        if not engine._table_exists(con, BATCH_TABLE):
            return None
        row = con.execute(
            f"SELECT * FROM {BATCH_TABLE} WHERE school_year_id=? AND level_code=? ORDER BY id DESC LIMIT 1",
            (int(school_year_id), str(level_code)),
        ).fetchone()
        return dict(row) if row is not None else None
    finally:
        con.close()


def _plan_title(plan: dict[str, Any]) -> str:
    text = str(plan.get("plan_text") or "").strip()
    if text:
        return text
    target = str((plan.get("target_school") or {}).get("name") or (plan.get("target_school") or {}).get("excel_name") or "").strip()
    return target or str(plan.get("id") or "Phương án")


def _plan_levels(plan: dict[str, Any]) -> set[str]:
    return {str(x or "").strip().upper() for x in (plan.get("level_codes") or []) if str(x or "").strip()}


def _clean_user_message(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    replacements = (
        ("V4.3", "kiểm tra dữ liệu nguồn"),
        ("V4.1", "bản xem trước"),
        ("MAPPED", "đã xác định nguồn → đích"),
        ("BLOCK", "CHẶN"),
        ("PASS", "ĐẠT"),
    )
    for old, new in replacements:
        text = text.replace(old, new)
    text = text.replace("không đạt kiểm tra nguồn kiểm tra dữ liệu nguồn", "không đạt kiểm tra dữ liệu nguồn")
    text = text.replace(
        "chỉ mở thực hiện cho phương án đã xác định nguồn → đích có nguồn → đích rõ ràng",
        "chỉ thực hiện khi đã xác định rõ trường nguồn → trường đích",
    )
    return text


def _norm_text(value: Any) -> str:
    text = str(value or "").strip().lower().replace("đ", "d")
    text = "".join(
        ch for ch in unicodedata.normalize("NFD", text)
        if unicodedata.category(ch) != "Mn"
    )
    text = text.replace("&", " va ")
    text = re.sub(r"[\-–—_/.,:;()]+", " ", text)
    text = re.sub(r"\btruong\b", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _load_level_lock() -> tuple[dict[str, Any], str]:
    if not LEVEL_LOCK_PATH.exists():
        raise SchoolMergerLevelBatchError(
            "Chưa cài bảng khóa cấp sáp nhập QĐ3805. Hãy cài qd3805_level_lock.json trước khi kiểm tra toàn cấp."
        )
    try:
        raw = LEVEL_LOCK_PATH.read_bytes()
        data = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise SchoolMergerLevelBatchError("Không đọc được bảng khóa cấp sáp nhập QĐ3805: " + str(exc)) from exc
    if str(data.get("schema") or "") != LEVEL_LOCK_SCHEMA:
        raise SchoolMergerLevelBatchError("Bảng khóa cấp sáp nhập không đúng schema QĐ3805 đã chốt.")
    if str(data.get("effective_school_year") or "") != LEVEL_LOCK_EFFECTIVE_YEAR:
        raise SchoolMergerLevelBatchError("Bảng khóa cấp sáp nhập không đúng năm hiệu lực 2026-2027.")
    return data, hashlib.sha256(raw).hexdigest()




def _load_resolution_file(path: Path, label: str) -> tuple[dict[str, Any], str]:
    if not path.exists():
        return {}, ""
    raw = path.read_bytes()
    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise SchoolMergerLevelBatchError(
            f"Không đọc được sổ xử lý riêng {label} QĐ3805: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise SchoolMergerLevelBatchError(
            f"Sổ xử lý riêng {label} QĐ3805 không đúng cấu trúc."
        )
    return payload, hashlib.sha256(raw).hexdigest()


def _resolution_context(level_code: str) -> dict[str, Any]:
    level = _level(level_code)
    if level == "TH":
        payload, fingerprint = _load_resolution_file(
            TH_RESOLUTION_PATH,
            "Tiểu học",
        )
    elif level == "MN":
        payload, fingerprint = _load_resolution_file(
            MN_RESOLUTION_PATH,
            "Mầm non",
        )
    else:
        payload, fingerprint = {}, ""

    return {
        "payload": payload,
        "fingerprint": fingerprint,
        "rename_only": [
            dict(x)
            for x in (payload.get("rename_only") or [])
            if isinstance(x, dict)
        ],
        "special_same_level": [
            dict(x)
            for x in (payload.get("special_same_level") or [])
            if isinstance(x, dict)
        ],
        "precompleted": [
            dict(x)
            for x in (payload.get("precompleted") or [])
            if isinstance(x, dict)
        ],
        "deferred_orphans": [
            dict(x)
            for x in (payload.get("deferred_orphans") or [])
            if isinstance(x, dict)
        ],
    }


def _active_staff_year_count(
    con: sqlite3.Connection,
    *,
    school_code: str,
    year_code: str,
) -> int:
    row = con.execute(
        "SELECT COUNT(*) AS n "
        "FROM staff_year_records syr "
        "JOIN staff_members sm ON sm.id=syr.staff_member_id "
        "JOIN schools s ON s.id=syr.school_id "
        "JOIN school_years sy ON sy.id=syr.school_year_id "
        "WHERE s.code=? "
        "AND REPLACE(REPLACE(sy.code,'–','-'),'—','-')=? "
        "AND COALESCE(syr.is_active,1)=1 "
        "AND COALESCE(sm.is_active,1)=1",
        (
            str(school_code or "").strip(),
            str(year_code or "").replace("–", "-").replace("—", "-"),
        ),
    ).fetchone()
    return int((row or {"n": 0})["n"] or 0)


def _precompleted_resolution_status(
    *,
    operation_id: str,
    resolution: dict[str, Any],
    audit_item: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    rule = next(
        (
            dict(x)
            for x in (resolution.get("precompleted") or [])
            if str((x or {}).get("operation_id") or "") == str(operation_id or "")
        ),
        None,
    )
    if not rule:
        return None

    source_code = str(rule.get("source_school_code") or "").strip()
    target_code = str(rule.get("target_school_code") or "").strip()
    previous_year_code = str(rule.get("previous_year_code") or "2025-2026")
    current_year_code = str(rule.get("current_year_code") or "2026-2027")

    con = engine._connect(read_only=True)
    try:
        source = con.execute(
            "SELECT id,code,name,is_active FROM schools WHERE code=? LIMIT 1",
            (source_code,),
        ).fetchone()
        target = con.execute(
            "SELECT id,code,name,is_active FROM schools WHERE code=? LIMIT 1",
            (target_code,),
        ).fetchone()
        if source is None or target is None:
            return {
                "pass": False,
                "operation_id": operation_id,
                "reason": "Không tìm thấy đủ trường nguồn/đích theo mã trong DB.",
            }

        evidence = {
            "source_school_id": int(source["id"]),
            "source_school_code": str(source["code"] or ""),
            "source_school_name": str(source["name"] or ""),
            "source_is_active": bool(source["is_active"]),
            "target_school_id": int(target["id"]),
            "target_school_code": str(target["code"] or ""),
            "target_school_name": str(target["name"] or ""),
            "target_is_active": bool(target["is_active"]),
            "previous_target_active": _active_staff_year_count(
                con, school_code=target_code, year_code=previous_year_code
            ),
            "previous_source_active": _active_staff_year_count(
                con, school_code=source_code, year_code=previous_year_code
            ),
            "current_target_active": _active_staff_year_count(
                con, school_code=target_code, year_code=current_year_code
            ),
            "current_source_active": _active_staff_year_count(
                con, school_code=source_code, year_code=current_year_code
            ),
        }
    finally:
        con.close()

    # Năm 2025-2026 phải dùng đúng "đủ điều kiện kế thừa" của source audit V4.3,
    # không dùng tổng staff_year_records is_active. Một số hồ sơ lịch sử vẫn is_active=1
    # nhưng trạng thái nguồn là chuyển đi/nghỉ việc nên không thuộc tập rollover.
    audit = dict(audit_item or {})
    school_checks = [
        dict(x) for x in (audit.get("school_checks") or [])
        if isinstance(x, dict)
    ]
    audit_target = next(
        (
            x for x in school_checks
            if str(x.get("role") or "").upper() == "TARGET"
            and str(x.get("school_code") or "").strip() == target_code
        ),
        None,
    )
    audit_source = next(
        (
            x for x in school_checks
            if str(x.get("role") or "").upper() == "SOURCE"
            and str(x.get("school_code") or "").strip() == source_code
        ),
        None,
    )

    previous_target_eligible = (
        int(audit_target.get("active_db_eligible") or 0)
        if audit_target is not None else -1
    )
    previous_source_eligible = (
        int(audit_source.get("active_db_eligible") or 0)
        if audit_source is not None else -1
    )
    evidence["source_audit_pass"] = bool(audit.get("pass"))
    evidence["previous_target_eligible"] = previous_target_eligible
    evidence["previous_source_eligible"] = previous_source_eligible

    expected = {
        "previous_target_active": int(rule.get("expected_previous_target_active") or 0),
        "previous_source_active": int(rule.get("expected_previous_source_active") or 0),
        "current_target_active": int(rule.get("expected_current_target_active") or 0),
        "current_source_active": int(rule.get("expected_current_source_active") or 0),
    }
    checks = {
        "source_inactive": evidence["source_is_active"] is False,
        "target_active": evidence["target_is_active"] is True,
        "source_audit_pass": evidence["source_audit_pass"] is True,
        "previous_target_eligible": previous_target_eligible == expected["previous_target_active"],
        "previous_source_eligible": previous_source_eligible == expected["previous_source_active"],
        "current_target_active": evidence["current_target_active"] == expected["current_target_active"],
        "current_source_active": evidence["current_source_active"] == expected["current_source_active"],
        "rollover_sum": evidence["current_target_active"] == (
            previous_target_eligible + previous_source_eligible
        ),
    }
    return {
        "pass": all(checks.values()),
        "operation_id": operation_id,
        "rule": rule,
        "evidence": evidence,
        "checks": checks,
        "reason": (
            "Nguồn đã khóa và số đội ngũ năm hiện hành tại đích khớp đúng tổng nguồn+đích năm trước."
            if all(checks.values())
            else "Dấu vết dữ liệu chưa đủ để coi là đã hoàn tất trước."
        ),
    }


def _deferred_unresolved_stt(resolution: dict[str, Any]) -> set[int]:
    out: set[int] = set()
    for item in (resolution.get("deferred_orphans") or []):
        value = _safe_int((item or {}).get("stt"))
        if value is not None:
            out.add(int(value))
    return out


def _registry_level_context(level_code: str) -> dict[str, Any]:
    level = _level(level_code)
    data, level_fingerprint = _load_level_lock()
    resolution = _resolution_context(level)
    operations = [dict(x) for x in (data.get("operations") or [])]
    orphans = [dict(x) for x in (data.get("orphans") or [])]

    rename_ids = {
        str(x.get("operation_id") or "")
        for x in (resolution.get("rename_only") or [])
        if str(x.get("operation_id") or "")
    }
    special_same_ids = {
        str(x.get("operation_id") or "")
        for x in (resolution.get("special_same_level") or [])
        if str(x.get("operation_id") or "")
    }

    pure_actions = [
        x for x in operations
        if str(x.get("batch") or "") == level
        and str(x.get("operation_id") or "") not in rename_ids
        and str(x.get("operation_id") or "") not in special_same_ids
    ]
    rename_ops: list[dict[str, Any]] = []
    for x in operations:
        if str(x.get("operation_id") or "") not in rename_ids:
            continue
        item = dict(x)
        rule = next(
            (
                r for r in (resolution.get("rename_only") or [])
                if str(r.get("operation_id") or "") == str(item.get("operation_id") or "")
            ),
            {},
        )
        item["batch"] = "LIÊN CẤP/ĐẶC THÙ"
        item["relation_type"] = str(rule.get("relation_type") or "ĐỔI TÊN – XỬ LÝ RIÊNG")
        item["official_plan"] = str(rule.get("display_title") or item.get("official_plan") or "")
        item["resolution_note"] = str(rule.get("reason") or "")
        rename_ops.append(item)


    special_same_ops: list[dict[str, Any]] = []
    for x in operations:
        if str(x.get("operation_id") or "") not in special_same_ids:
            continue
        item = dict(x)
        rule = next(
            (
                r
                for r in (resolution.get("special_same_level") or [])
                if str(r.get("operation_id") or "")
                == str(item.get("operation_id") or "")
            ),
            {},
        )
        item["batch"] = "ĐẶC THÙ CÙNG CẤP"
        item["relation_type"] = str(
            rule.get("relation_type")
            or "ĐẶC THÙ CÙNG CẤP – XỬ LÝ RIÊNG"
        )
        item["official_plan"] = str(
            rule.get("display_title")
            or item.get("official_plan")
            or ""
        )
        item["resolution_note"] = str(rule.get("reason") or "")
        item["special_kind"] = "SAME_LEVEL_SPECIAL"
        special_same_ops.append(item)

    keep_ops = [
        x for x in operations
        if str(x.get("batch") or "") == "GIỮ NGUYÊN"
        and set(str(v or "").upper() for v in (x.get("source_levels") or [])) == {level}
    ]
    special_ops = [
        x for x in operations
        if str(x.get("batch") or "") == "LIÊN CẤP/ĐẶC THÙ"
        and level in {
            str(v or "").upper()
            for v in ((x.get("source_levels") or []) + (x.get("target_levels") or []))
        }
    ] + rename_ops + special_same_ops
    unresolved = [
        x for x in orphans
        if str(x.get("batch") or "") == "CẦN ĐỐI CHIẾU"
        and level in {str(v or "").upper() for v in (x.get("source_levels") or [])}
    ]
    special_orphans = [
        x for x in orphans
        if str(x.get("batch") or "") == "LIÊN CẤP/ĐẶC THÙ"
        and level in {str(v or "").upper() for v in (x.get("source_levels") or [])}
    ]
    deferred_stt = _deferred_unresolved_stt(resolution)
    for x in orphans:
        stt = _safe_int(x.get("stt"))
        if stt is None or int(stt) not in deferred_stt:
            continue
        item = dict(x)
        rule = next(
            (
                r for r in (resolution.get("deferred_orphans") or [])
                if _safe_int(r.get("stt")) == stt
            ),
            {},
        )
        item["batch"] = "LIÊN CẤP/ĐẶC THÙ"
        item["status"] = str(
            rule.get("status")
            or "CHỜ XÁC NHẬN – KHÔNG TÁC ĐỘNG TRONG SÁP NHẬP TOÀN CẤP"
        )
        item["note"] = str(rule.get("display_title") or item.get("school") or "")
        special_orphans.append(item)

    combined_fingerprint = _json_hash({
        "level_lock": level_fingerprint,
        "resolution": str(resolution.get("fingerprint") or ""),
    })
    return {
        "data": data,
        "fingerprint": combined_fingerprint,
        "level_lock_fingerprint": level_fingerprint,
        "resolution": resolution,
        "pure_actions": pure_actions,
        "keep_ops": keep_ops,
        "special_ops": special_ops,
        "same_level_special_ops": special_same_ops,
        "unresolved": unresolved,
        "special_orphans": special_orphans,
    }

def registry_level_summary(level_code: str) -> dict[str, Any]:
    ctx = _registry_level_context(level_code)
    return {
        "level_code": _level(level_code),
        "schema": LEVEL_LOCK_SCHEMA,
        "fingerprint": ctx["fingerprint"],
        "action_count": len(ctx["pure_actions"]),
        "keep_count": len(ctx["keep_ops"]),
        "special_count": len(ctx["special_ops"]) + len(ctx["special_orphans"]),
        "unresolved_count": len(ctx["unresolved"]),
    }


def _plan_stt_values(plan: dict[str, Any]) -> set[int]:
    first = _safe_int(plan.get("first_stt"))
    last = _safe_int(plan.get("last_stt"))
    if first is None and last is None:
        return set()
    if first is None:
        return {int(last)}
    if last is None:
        return {int(first)}
    lo, hi = sorted((int(first), int(last)))
    if hi - lo <= 30:
        return set(range(lo, hi + 1))
    return {lo, hi}


def _plan_member_names(plan: dict[str, Any]) -> set[str]:
    out: set[str] = set()
    for item in (plan.get("member_schools") or []):
        name = str((item or {}).get("excel_name") or (item or {}).get("name") or "").strip()
        if name:
            out.add(_norm_text(name))
    return out


def _op_stt_values(op: dict[str, Any]) -> set[int]:
    out: set[int] = set()
    for value in (op.get("stt_members") or []):
        iv = _safe_int(value)
        if iv is not None:
            out.add(iv)
    return out


def _op_member_names(op: dict[str, Any]) -> set[str]:
    return {
        _norm_text((item or {}).get("name"))
        for item in (op.get("source_schools") or [])
        if str((item or {}).get("name") or "").strip()
    }


def _match_registry_operation(
    plan: dict[str, Any],
    operations: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, str]:
    pstt = _plan_stt_values(plan)
    pnames = _plan_member_names(plan)
    ptext = _norm_text(plan.get("plan_text"))
    pcommune = _norm_text(plan.get("commune_excel"))

    scored: list[tuple[int, dict[str, Any]]] = []
    for op in operations:
        ostt = _op_stt_values(op)
        onames = _op_member_names(op)
        overlap_stt = pstt & ostt
        overlap_names = pnames & onames
        if not overlap_stt and not overlap_names:
            continue
        score = 0
        if overlap_stt:
            score += 500 + 20 * len(overlap_stt)
            if pstt and ostt and pstt == ostt:
                score += 120
        if overlap_names:
            score += 80 * len(overlap_names)
            if pnames and onames and pnames == onames:
                score += 160
        if ptext and ptext == _norm_text(op.get("official_plan")):
            score += 90
        if pcommune and pcommune == _norm_text(op.get("commune")):
            score += 30
        scored.append((score, op))

    if not scored:
        return None, "Không tìm thấy operation QĐ3805 tương ứng theo STT/tên trường."
    scored.sort(key=lambda x: (x[0], str(x[1].get("operation_id") or "")), reverse=True)
    best_score = scored[0][0]
    best = [op for score, op in scored if score == best_score]
    if len(best) != 1:
        return None, "Có nhiều operation QĐ3805 cùng mức khớp; hệ thống không tự chọn."
    return best[0], ""


def _registry_special_view(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for op in ctx.get("special_ops") or []:
        levels = sorted(set(
            [str(x or "").upper() for x in (op.get("source_levels") or [])]
            + [str(x or "").upper() for x in (op.get("target_levels") or [])]
        ))
        out.append({
            "operation_id": str(op.get("operation_id") or ""),
            "commune": str(op.get("commune") or ""),
            "title": str(op.get("official_plan") or "Phương án liên cấp/đặc thù"),
            "levels": levels,
            "relation": str(op.get("relation_type") or "LIÊN CẤP/ĐẶC THÙ"),
            "special_kind": str(op.get("special_kind") or "CROSS_LEVEL_OR_OTHER"),
        })
    for row in ctx.get("special_orphans") or []:
        out.append({
            "operation_id": str(row.get("operation_id") or ""),
            "commune": str(row.get("commune") or ""),
            "title": str(row.get("note") or row.get("school") or "Dòng đặc thù"),
            "levels": [str(x or "").upper() for x in (row.get("source_levels") or [])],
            "relation": str(row.get("status") or "LIÊN CẤP/ĐẶC THÙ"),
        })
    return out


def _state_rows(
    school_year_id: int,
    level_code: str,
) -> tuple[list[dict[str, Any]], dict[str, int], list[dict[str, Any]], dict[str, Any]]:
    level = _level(level_code)
    ctx = _registry_level_context(level)
    resolution = dict(ctx.get("resolution") or {})
    pure_ops = list(ctx["pure_actions"])
    keep_ops = list(ctx["keep_ops"])
    special_ops = list(ctx["special_ops"])
    allowed_ops = pure_ops + keep_ops + special_ops

    plans = list_official_registry_plans(
        school_year_id=int(school_year_id),
        commune_id=None,
        level_code=level,
        display_mode="all",
    )
    plans = annotate_official_plan_execution_status(plans)

    audit = audit_official_plans(
        school_year_id=int(school_year_id),
        commune_id=None,
        level_code=level,
    )
    audit_map = {
        str((row.get("plan") or {}).get("id") or ""): dict(row.get("audit") or {})
        for row in (audit.get("rows") or [])
    }

    pure_ids = {str(x.get("operation_id") or "") for x in pure_ops}
    keep_ids = {str(x.get("operation_id") or "") for x in keep_ops}
    special_ids = {str(x.get("operation_id") or "") for x in special_ops}

    rows: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    counts = {"KEEP": len(keep_ops), "DONE": 0, "READY": 0, "BLOCK": 0}
    mapped_action_ids: set[str] = set()
    mapped_keep_ids: set[str] = set()
    op_to_plan_ids: dict[str, list[str]] = {}
    current_unmapped: list[dict[str, Any]] = []
    special_current: list[dict[str, Any]] = []

    for raw in plans:
        plan = dict(raw)
        pid = str(plan.get("id") or "")
        op, match_error = _match_registry_operation(plan, allowed_ops)
        if op is None:
            current_unmapped.append({
                "plan_id": pid,
                "title": _plan_title(plan),
                "commune": str(plan.get("commune_excel") or ""),
                "reason": match_error,
            })
            continue

        op_id = str(op.get("operation_id") or "")
        op_to_plan_ids.setdefault(op_id, []).append(pid)
        batch = str(op.get("batch") or "")
        plan["qd3805_operation_id"] = op_id
        plan["qd3805_batch"] = batch
        plan["qd3805_relation_type"] = str(op.get("relation_type") or "")

        if op_id in special_ids or batch == "LIÊN CẤP/ĐẶC THÙ":
            special_current.append(plan)
            continue

        audit_item = audit_map.get(pid) or {}
        blockers: list[str] = []
        execution_status = str(plan.get("execution_status") or "").upper().strip()
        action = str(plan.get("action_type") or "").upper().strip()
        precompleted = _precompleted_resolution_status(
            operation_id=op_id,
            resolution=resolution,
            audit_item=audit_item,
        )

        if op_id in keep_ids or batch == "GIỮ NGUYÊN":
            mapped_keep_ids.add(op_id)
            state = "KEEP"
            label = "GIỮ NGUYÊN"
        elif op_id in pure_ids and batch == level:
            mapped_action_ids.add(op_id)
            if precompleted is not None and bool(precompleted.get("pass")):
                state = "DONE"
                label = "ĐÃ HOÀN TẤT TRƯỚC – KHÔNG CHẠY LẠI"
                counts["DONE"] += 1
                plan["qd3805_precompleted"] = precompleted
            elif execution_status.startswith("COMPLETED"):
                state = "DONE"
                label = "ĐÃ THỰC HIỆN"
                counts["DONE"] += 1
            elif (
                action == "MAPPED"
                and str(plan.get("match_status") or "") == "MATCHED"
                and bool(audit_item.get("pass"))
            ):
                state = "READY"
                label = "ĐẠT KIỂM TRA NGUỒN"
                counts["READY"] += 1
                candidates.append(plan)
            else:
                state = "BLOCK"
                label = "CHẶN – CẦN XỬ LÝ"
                counts["BLOCK"] += 1
                blockers.extend(
                    _clean_user_message(x)
                    for x in (audit_item.get("blockers") or [])
                    if str(x).strip()
                )
                if action == "KEEP":
                    blockers.insert(0, "QĐ3805 xác định đây là phương án cần tác động nhưng registry cũ đang đánh dấu GIỮ NGUYÊN.")
                if str(plan.get("match_status") or "") != "MATCHED":
                    match_text = str(plan.get("match_label") or "").strip()
                    if match_text:
                        blockers.insert(0, _clean_user_message(match_text))
                if not blockers:
                    blockers.append("Phương án chưa đủ điều kiện để thực hiện.")
        else:
            current_unmapped.append({
                "plan_id": pid,
                "title": _plan_title(plan),
                "commune": str(plan.get("commune_excel") or ""),
                "reason": "Operation QĐ3805 không thuộc batch thuần đang chọn.",
            })
            continue

        plan.update({
            "batch_state": state,
            "batch_label": label,
            "batch_blockers": blockers,
            "source_audit": audit_item,
        })
        rows.append(plan)

    duplicate_mappings = [
        {"operation_id": op_id, "plan_ids": sorted(set(pids))}
        for op_id, pids in op_to_plan_ids.items()
        if len(set(pids)) > 1 and op_id in pure_ids
    ]
    duplicate_ids = {x["operation_id"] for x in duplicate_mappings}
    if duplicate_ids:
        candidates = [p for p in candidates if str(p.get("qd3805_operation_id") or "") not in duplicate_ids]
        # Một operation QĐ3805 chỉ được tính đúng một lần. Nếu cùng operation ghép vào
        # nhiều phương án nội bộ thì toàn bộ các dòng liên quan chuyển sang BLOCK.
        duplicate_plan_map = {
            str(x.get("operation_id") or ""): list(x.get("plan_ids") or [])
            for x in duplicate_mappings
        }
        for plan in rows:
            op_id = str(plan.get("qd3805_operation_id") or "")
            if op_id not in duplicate_ids:
                continue
            plan["batch_state"] = "BLOCK"
            plan["batch_label"] = "CHẶN – TRÙNG GHÉP QĐ3805"
            msg = (
                f"Operation QĐ3805 {op_id} đang ghép vào nhiều phương án nội bộ: "
                + ", ".join(duplicate_plan_map.get(op_id) or [])
                + ". Hệ thống chỉ tính operation này một lần và tuyệt đối không cho chạy cho đến khi xử lý trùng ghép."
            )
            blockers = list(plan.get("batch_blockers") or [])
            if msg not in blockers:
                blockers.insert(0, msg)
            plan["batch_blockers"] = blockers

    # Chuẩn hóa KPI theo operation QĐ3805 DUY NHẤT, không theo số dòng phương án nội bộ.
    # Nhờ vậy DONE + READY + BLOCK luôn bằng số operation QĐ3805 đã ghép ở batch thuần.
    action_state_by_op: dict[str, str] = {}
    for plan in rows:
        op_id = str(plan.get("qd3805_operation_id") or "")
        if op_id not in pure_ids:
            continue
        state = str(plan.get("batch_state") or "BLOCK").upper().strip()
        if op_id in duplicate_ids:
            state = "BLOCK"
        previous = action_state_by_op.get(op_id)
        if previous is None:
            action_state_by_op[op_id] = state
        elif previous != state:
            action_state_by_op[op_id] = "BLOCK"

    counts["DONE"] = sum(1 for x in action_state_by_op.values() if x == "DONE")
    counts["READY"] = sum(1 for x in action_state_by_op.values() if x == "READY")
    counts["BLOCK"] = sum(1 for x in action_state_by_op.values() if x == "BLOCK")

    missing_action_ops = [x for x in pure_ops if str(x.get("operation_id") or "") not in mapped_action_ids]
    missing_keep_ops = [x for x in keep_ops if str(x.get("operation_id") or "") not in mapped_keep_ids]

    lock_meta = {
        "schema": LEVEL_LOCK_SCHEMA,
        "fingerprint": ctx["fingerprint"],
        "expected_action_count": len(pure_ops),
        "expected_keep_count": len(keep_ops),
        "mapped_action_count": len(mapped_action_ids),
        "mapped_keep_count": len(mapped_keep_ids),
        "missing_action_ops": missing_action_ops,
        "missing_keep_ops": missing_keep_ops,
        "duplicate_mappings": duplicate_mappings,
        "unresolved_orphans": list(ctx["unresolved"]),
        "current_unmapped": current_unmapped,
        "special_current": special_current,
        "special_registry": _registry_special_view(ctx),
        "resolution": resolution,
    }
    return rows, counts, candidates, lock_meta


def build_level_batch_preview(*, school_year_id: int, level_code: str) -> dict[str, Any]:
    level = _level(level_code)
    year = _year_info(int(school_year_id))
    rows, counts, candidates, lock_meta = _state_rows(int(school_year_id), level)
    previous_batch = _existing_batch(int(school_year_id), level)
    resolution = dict(lock_meta.get("resolution") or {})
    deferred_unresolved_stt = _deferred_unresolved_stt(resolution)

    detail_by_id: dict[str, dict[str, Any]] = {}
    extra_blockers: list[dict[str, Any]] = []
    used_school: dict[int, list[str]] = {}

    for item in lock_meta.get("missing_action_ops") or []:
        extra_blockers.append({
            "plan_id": "",
            "title": "Chưa ghép được phương án QĐ3805 vào engine hiện tại",
            "reasons": [
                f"{item.get('operation_id')}: {item.get('commune') or ''} – {item.get('official_plan') or 'Phương án'}"
            ],
        })
    for item in lock_meta.get("unresolved_orphans") or []:
        stt = _safe_int(item.get("stt"))
        if stt is not None and int(stt) in deferred_unresolved_stt:
            continue
        extra_blockers.append({
            "plan_id": "",
            "title": "Dòng QĐ3805 chưa có phương án đủ rõ",
            "reasons": [
                f"STT {item.get('stt')}: {item.get('school') or ''} – {item.get('commune') or ''}. "
                "Không tự suy đoán nguồn/đích; cần xác nhận nghiệp vụ trước khi mở toàn cấp."
            ],
        })
    for item in lock_meta.get("duplicate_mappings") or []:
        extra_blockers.append({
            "plan_id": "",
            "title": "Một operation QĐ3805 đang ghép vào nhiều phương án nội bộ",
            "reasons": [
                f"{item.get('operation_id')}: {', '.join(item.get('plan_ids') or [])}. Hệ thống chặn để tránh chạy lặp."
            ],
        })

    # Chỉ dựng bản xem trước chi tiết cho các phương án thuần đã qua cổng nguồn và đã được QĐ3805 khóa đúng batch.
    for plan in candidates:
        pid = str(plan.get("id") or "")
        try:
            detail = build_official_plan_impact_preview(pid)
        except Exception as exc:
            detail = None
            extra_blockers.append({
                "plan_id": pid,
                "title": _plan_title(plan),
                "reasons": ["Không lập được bản xem trước an toàn: " + str(exc)],
            })
        if detail is None:
            continue
        detail_by_id[pid] = detail
        reasons: list[str] = []
        if detail.get("keep_only"):
            reasons.append("QĐ3805 xác định cần tác động nhưng bản xem trước nội bộ đang nhận là GIỮ NGUYÊN.")
        if not detail.get("safe_for_future_execution"):
            reasons.extend(_clean_user_message(x) for x in (detail.get("blockers") or []) if str(x).strip())
        if not detail.get("simulation_ok"):
            reasons.append("Mô phỏng chưa đạt.")
        if not detail.get("v41_state_check_ok"):
            reasons.append("Bản xem trước chưa khóa được trạng thái dữ liệu.")
        if not detail.get("v43_source_check_ok"):
            reasons.append("Kiểm tra dữ liệu nguồn chưa đạt.")
        if detail.get("completed_operation"):
            reasons.append("Phương án đã có nhật ký thực hiện và không được chạy lại.")
        if reasons:
            extra_blockers.append({
                "plan_id": pid,
                "title": _plan_title(plan),
                "reasons": list(dict.fromkeys(reasons)),
            })

        ids: list[int] = []
        target_id = _safe_int((detail.get("target_school") or {}).get("id"))
        if target_id is not None:
            ids.append(target_id)
        ids.extend(
            int(x.get("id"))
            for x in (detail.get("source_schools") or [])
            if _safe_int((x or {}).get("id")) is not None
        )
        for sid in sorted(set(ids)):
            used_school.setdefault(sid, []).append(pid)

    overlap_items = [
        {"school_id": sid, "plan_ids": pids}
        for sid, pids in used_school.items()
        if len(set(pids)) > 1
    ]
    if overlap_items:
        extra_blockers.append({
            "plan_id": "",
            "title": "Trùng phạm vi giữa các phương án",
            "reasons": [
                "Một trường xuất hiện trong nhiều phương án cần thực hiện của cùng cấp. "
                "Hệ thống chặn sáp nhập toàn cấp để tránh phụ thuộc thứ tự."
            ],
        })

    detailed_block_plan_ids = {
        str(x.get("plan_id") or "")
        for x in extra_blockers
        if str(x.get("plan_id") or "")
    }
    effective_ready = [
        p for p in candidates
        if str(p.get("id") or "") not in detailed_block_plan_ids
    ]

    # duplicate_mappings đã được quy về BLOCK đúng một operation ở counts["BLOCK"],
    # nên không cộng lần thứ hai vào registry_block_count.
    blocking_unresolved = [
        x for x in (lock_meta.get("unresolved_orphans") or [])
        if _safe_int(x.get("stt")) is None
        or int(_safe_int(x.get("stt"))) not in deferred_unresolved_stt
    ]
    registry_block_count = (
        len(lock_meta.get("missing_action_ops") or [])
        + len(blocking_unresolved)
    )
    effective_block_count = (
        int(counts["BLOCK"])
        + len(detailed_block_plan_ids)
        + registry_block_count
        + (1 if overlap_items else 0)
    )

    fingerprint_rows: list[dict[str, Any]] = []
    for plan in rows:
        pid = str(plan.get("id") or "")
        state = str(plan.get("batch_state") or "")
        item: dict[str, Any] = {
            "plan_id": pid,
            "state": state,
            "qd3805_operation_id": str(plan.get("qd3805_operation_id") or ""),
        }
        detail = detail_by_id.get(pid)
        if detail is not None:
            item.update({
                "impact": str(detail.get("impact_state_fingerprint") or ""),
                "source": str((detail.get("source_audit") or {}).get("fingerprint") or ""),
                "preview": str(detail.get("fingerprint") or ""),
                "safe": bool(detail.get("safe_for_future_execution")),
                "simulation": bool(detail.get("simulation_ok")),
            })
        fingerprint_rows.append(item)

    batch_fingerprint = _json_hash({
        "school_year_id": int(school_year_id),
        "level_code": level,
        "qd3805_registry_fingerprint": lock_meta.get("fingerprint"),
        "rows": fingerprint_rows,
        "overlap": overlap_items,
        "missing_action_ids": [x.get("operation_id") for x in (lock_meta.get("missing_action_ops") or [])],
        "unresolved_ids": [x.get("operation_id") for x in (lock_meta.get("unresolved_orphans") or [])],
    })

    candidate_views: list[dict[str, Any]] = []
    for plan in effective_ready:
        pid = str(plan.get("id") or "")
        detail = detail_by_id.get(pid) or {}
        candidate_views.append({
            "plan_id": pid,
            "qd3805_operation_id": str(plan.get("qd3805_operation_id") or ""),
            "commune": str(plan.get("commune_excel") or ""),
            "title": _plan_title(plan),
            "sources": [
                str(x.get("name") or x.get("excel_name") or "")
                for x in (detail.get("source_schools") or [])
            ],
            "target": str(
                (detail.get("target_school") or {}).get("name")
                or (detail.get("target_school") or {}).get("excel_name")
                or ""
            ),
            "impact_fingerprint": str(detail.get("impact_state_fingerprint") or ""),
            "source_fingerprint": str((detail.get("source_audit") or {}).get("fingerprint") or ""),
            "summary": dict(detail.get("summary") or {}),
        })

    action_expected = int(lock_meta.get("expected_action_count") or 0)
    mapped_actions = int(lock_meta.get("mapped_action_count") or 0)
    ready_for_execution = (
        previous_batch is None
        and effective_block_count == 0
        and len(effective_ready) > 0
        and len(effective_ready) == counts["READY"]
        and mapped_actions == action_expected
    )
    all_done = (
        action_expected > 0
        and counts["DONE"] == action_expected
        and effective_block_count == 0
    )

    return {
        "school_year": year,
        "school_year_id": int(school_year_id),
        "level_code": level,
        "counts": counts,
        "total": action_expected + int(lock_meta.get("expected_keep_count") or 0),
        "rows": rows,
        "registry": lock_meta,
        "registry_action_expected_count": action_expected,
        "registry_keep_expected_count": int(lock_meta.get("expected_keep_count") or 0),
        "registry_action_mapped_count": mapped_actions,
        "registry_keep_mapped_count": int(lock_meta.get("mapped_keep_count") or 0),
        "registry_unmapped_count": len(lock_meta.get("missing_action_ops") or []),
        "registry_unresolved_count": len(lock_meta.get("unresolved_orphans") or []),
        "registry_duplicate_mapping_count": len(lock_meta.get("duplicate_mappings") or []),
        "resolution": resolution,
        "registry_deferred_unresolved_count": sum(
            1 for x in (lock_meta.get("unresolved_orphans") or [])
            if _safe_int(x.get("stt")) is not None
            and int(_safe_int(x.get("stt"))) in deferred_unresolved_stt
        ),
        "excluded_cross_level": [
            x for x in (lock_meta.get("special_registry") or [])
            if str((x or {}).get("special_kind") or "") != "SAME_LEVEL_SPECIAL"
        ],
        "excluded_cross_level_count": sum(
            1 for x in (lock_meta.get("special_registry") or [])
            if str((x or {}).get("special_kind") or "") != "SAME_LEVEL_SPECIAL"
        ),
        "excluded_same_level_special": [
            x for x in (lock_meta.get("special_registry") or [])
            if str((x or {}).get("special_kind") or "") == "SAME_LEVEL_SPECIAL"
        ],
        "excluded_same_level_special_count": sum(
            1 for x in (lock_meta.get("special_registry") or [])
            if str((x or {}).get("special_kind") or "") == "SAME_LEVEL_SPECIAL"
        ),
        "registry_action_total_count": (
            int(lock_meta.get("expected_action_count") or 0)
            + sum(
                1 for x in (lock_meta.get("special_registry") or [])
                if str((x or {}).get("special_kind") or "") == "SAME_LEVEL_SPECIAL"
            )
        ),
        "scope_note": (
            "Mầm non không có liên cấp. Các trường hợp tiếp nhận điểm/lớp là đặc thù cùng cấp và xử lý riêng."
            if level == "MN"
            else "Batch MN/TH/THCS được khóa trực tiếp bằng registry QĐ3805; không suy đoán cấp từ tên trường."
        ),
        "candidates": candidate_views,
        "candidate_count": len(effective_ready),
        "effective_block_count": effective_block_count,
        "extra_blockers": extra_blockers,
        "overlap_items": overlap_items,
        "batch_fingerprint": batch_fingerprint,
        "ready_for_execution": ready_for_execution,
        "all_done": all_done,
        "previous_batch": previous_batch,
    }


def _ensure_tables(con: sqlite3.Connection) -> None:
    con.execute(
        "CREATE TABLE IF NOT EXISTS school_merger_operations ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "school_year_id INTEGER NOT NULL,"
        "target_school_id INTEGER NOT NULL,"
        "source_school_ids_json TEXT NOT NULL,"
        "actor_user_id INTEGER,"
        "backup_name TEXT,"
        "summary_json TEXT NOT NULL,"
        "created_at DATETIME NOT NULL"
        ")"
    )
    con.execute(
        f"CREATE TABLE IF NOT EXISTS {OFFICIAL_EXECUTION_TABLE} ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "plan_id TEXT NOT NULL UNIQUE,"
        "operation_id INTEGER,"
        "school_year_id INTEGER NOT NULL,"
        "target_school_id INTEGER NOT NULL,"
        "source_school_ids_json TEXT NOT NULL,"
        "actor_user_id INTEGER,"
        "actor_username TEXT,"
        "actor_full_name TEXT,"
        "backup_name TEXT NOT NULL,"
        "preview_fingerprint TEXT NOT NULL,"
        "summary_json TEXT NOT NULL,"
        "created_at DATETIME NOT NULL"
        ")"
    )
    con.execute(
        f"CREATE TABLE IF NOT EXISTS {BATCH_TABLE} ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "school_year_id INTEGER NOT NULL,"
        "level_code TEXT NOT NULL,"
        "actor_user_id INTEGER,"
        "actor_username TEXT,"
        "actor_full_name TEXT,"
        "backup_name TEXT NOT NULL,"
        "batch_fingerprint TEXT NOT NULL,"
        "total_plans INTEGER NOT NULL,"
        "keep_count INTEGER NOT NULL,"
        "done_before_count INTEGER NOT NULL,"
        "executed_count INTEGER NOT NULL,"
        "summary_json TEXT NOT NULL,"
        "created_at DATETIME NOT NULL"
        ")"
    )
    con.execute(
        f"CREATE UNIQUE INDEX IF NOT EXISTS uq_{BATCH_TABLE}_year_level "
        f"ON {BATCH_TABLE}(school_year_id, level_code)"
    )


def _already_done_locked(
    con: sqlite3.Connection,
    *,
    plan_id: str,
    school_year_id: int,
    target_school_id: int,
    source_ids: list[int],
) -> bool:
    if engine._table_exists(con, OFFICIAL_EXECUTION_TABLE):
        row = con.execute(
            f"SELECT id FROM {OFFICIAL_EXECUTION_TABLE} WHERE plan_id=? LIMIT 1",
            (str(plan_id),),
        ).fetchone()
        if row is not None:
            return True
    if not engine._table_exists(con, "school_merger_operations"):
        return False
    rows = con.execute(
        "SELECT source_school_ids_json FROM school_merger_operations "
        "WHERE school_year_id=? AND target_school_id=?",
        (int(school_year_id), int(target_school_id)),
    ).fetchall()
    wanted = sorted(set(int(x) for x in source_ids))
    for row in rows:
        try:
            got = sorted(set(int(x) for x in json.loads(row["source_school_ids_json"] or "[]")))
        except Exception:
            continue
        if got == wanted:
            return True
    return False


def _backup_locked_snapshot(
    *,
    school_year_id: int,
    level_code: str,
    batch_fingerprint: str,
    actor: dict[str, Any],
    candidate_count: int,
) -> tuple[Path, str]:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    folder = EXPORT_DIR / f"backup_truoc_sap_nhap_toan_cap_{stamp}_{_safe_folder_piece(level_code)}"
    folder.mkdir(parents=True, exist_ok=False)
    db_target = folder / "phocap.db"

    src = engine._connect(read_only=True)
    dst = sqlite3.connect(str(db_target), timeout=30)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()

    chk = sqlite3.connect(str(db_target), timeout=30)
    try:
        chk.row_factory = sqlite3.Row
        chk.execute("PRAGMA foreign_keys=ON")
        integrity = str(chk.execute("PRAGMA integrity_check").fetchone()[0])
        fk = chk.execute("PRAGMA foreign_key_check").fetchall()
        if integrity.lower() != "ok" or fk:
            raise SchoolMergerLevelBatchError(
                f"Backup trước sáp nhập không đạt kiểm tra: integrity={integrity}; fk={len(fk)}"
            )
    finally:
        chk.close()

    meta = {
        "backup_type": "automatic_before_level_school_merger_batch",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "school_year_id": int(school_year_id),
        "level_code": level_code,
        "candidate_count": int(candidate_count),
        "batch_fingerprint": batch_fingerprint,
        "actor": {
            "id": actor.get("id"),
            "username": actor.get("username"),
            "full_name": actor.get("full_name"),
            "role_code": actor.get("role_code"),
        },
        "database_backup": str(db_target),
        "status": "CREATED_BEFORE_TRANSACTION_MUTATION",
    }
    (folder / "thong_tin_sap_nhap_toan_cap.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return folder, folder.name


def execute_level_batch(
    *,
    school_year_id: int,
    level_code: str,
    actor: dict[str, Any],
    expected_batch_fingerprint: str,
    confirmation_scope: str,
    confirmation_text: str,
) -> dict[str, Any]:
    """Thực hiện một batch toàn cấp với 1 transaction ghi duy nhất.

    Quy tắc khóa:
    - Toàn bộ preview/mô phỏng/backup SQLite được làm TRƯỚC BEGIN IMMEDIATE.
    - Sau khi lấy write lock, tuyệt đối không mở preview bằng connection khác.
    - Dùng fingerprint vật lý main DB + WAL để chặn thay đổi giữa preflight và write lock.
    - Trong transaction chỉ dùng chính connection đang giữ write lock.
    """
    level = _level(level_code)
    if str(confirmation_scope or "").strip().lower() != "yes":
        raise SchoolMergerLevelBatchError("Bạn chưa đánh dấu xác nhận thực hiện sáp nhập toàn cấp.")
    if str(confirmation_text or "").strip().upper() != LEVEL_BATCH_CONFIRM_PHRASE:
        raise SchoolMergerLevelBatchError(
            f"Câu xác nhận chưa đúng. Hãy nhập chính xác: {LEVEL_BATCH_CONFIRM_PHRASE}"
        )
    if not str(expected_batch_fingerprint or "").strip():
        raise SchoolMergerLevelBatchError("Thiếu trạng thái khóa của bản xem trước toàn cấp. Hãy xem trước lại.")

    # ------------------------------------------------------------------
    # GIAI ĐOẠN 1 - PREFLIGHT CHỈ ĐỌC, CHƯA GIỮ WRITE LOCK
    # ------------------------------------------------------------------
    preflight = build_level_batch_preview(
        school_year_id=int(school_year_id),
        level_code=level,
    )
    if preflight.get("previous_batch") is not None:
        raise SchoolMergerLevelBatchError("Cấp học này đã có nhật ký sáp nhập toàn cấp; không được chạy lần hai.")
    if not preflight.get("ready_for_execution"):
        raise SchoolMergerLevelBatchError(
            "Toàn cấp chưa đạt điều kiện thực hiện. Hãy xử lý hết các phương án CHẶN và xem trước lại."
        )

    current_fp = str(preflight.get("batch_fingerprint") or "")
    if current_fp != str(expected_batch_fingerprint):
        raise SchoolMergerLevelBatchError(
            "Dữ liệu hoặc trạng thái phương án đã thay đổi kể từ lúc xem trước. "
            "Hệ thống đã chặn ghi; hãy KIỂM TRA SẴN SÀNG TOÀN CẤP lại."
        )

    candidates = list(preflight.get("candidates") or [])
    if not candidates:
        raise SchoolMergerLevelBatchError("Không còn phương án nào cần thực hiện trong cấp học này.")
    if preflight.get("overlap_items"):
        raise SchoolMergerLevelBatchError(
            "Các phương án READY còn chồng lấn trường nguồn/đích; không được thực hiện chung một batch."
        )

    # Dựng và khóa chi tiết từng candidate trước write lock.
    # Đây chính là chỗ bản cũ làm BÊN TRONG BEGIN IMMEDIATE và gây 'database is locked'.
    detail_by_plan: dict[str, dict[str, Any]] = {}
    database_fingerprints: set[str] = set()

    for item in candidates:
        pid = str(item.get("plan_id") or "").strip()
        if not pid:
            raise SchoolMergerLevelBatchError("Có candidate thiếu plan_id; dừng an toàn.")
        try:
            detail = build_official_plan_impact_preview(pid)
        except (SchoolMergerPreviewError, engine.SchoolMergerError, sqlite3.Error) as exc:
            raise SchoolMergerLevelBatchError(
                f"Phương án {pid}: không dựng được preflight an toàn: {exc}"
            ) from exc

        if (
            not detail.get("safe_for_future_execution")
            or not detail.get("simulation_ok")
            or not detail.get("v41_state_check_ok")
            or not detail.get("v43_source_check_ok")
            or detail.get("completed_operation")
        ):
            raise SchoolMergerLevelBatchError(
                f"Phương án {pid}: preflight an toàn không còn đạt; dừng toàn cấp."
            )

        target_id = _safe_int((detail.get("target_school") or {}).get("id"))
        source_ids = sorted(
            set(
                int(x.get("id"))
                for x in (detail.get("source_schools") or [])
                if _safe_int((x or {}).get("id")) is not None
            )
        )
        if target_id is None or not source_ids:
            raise SchoolMergerLevelBatchError(f"Phương án {pid}: thiếu trường nguồn hoặc trường đích.")

        detail_by_plan[pid] = detail
        dbfp = str(detail.get("database_fingerprint") or "").strip()
        if not dbfp:
            raise SchoolMergerLevelBatchError(f"Phương án {pid}: thiếu database fingerprint.")
        database_fingerprints.add(dbfp)

    if len(database_fingerprints) != 1:
        raise SchoolMergerLevelBatchError(
            "Database thay đổi trong lúc dựng preflight nhiều phương án. "
            "Hãy kiểm tra sẵn sàng toàn cấp lại."
        )
    preflight_db_fingerprint = next(iter(database_fingerprints))

    # Đối chiếu fingerprint ngay trước backup.
    if _preview_database_state_fingerprint() != preflight_db_fingerprint:
        raise SchoolMergerLevelBatchError(
            "Database đã thay đổi sau preflight và trước backup. Hệ thống chưa ghi dữ liệu."
        )

    # Backup phải làm trước BEGIN IMMEDIATE để SQLite Backup API không cạnh tranh
    # với write lock do chính request này đang giữ.
    backup_dir: Path | None = None
    backup_name = ""
    backup_dir, backup_name = _backup_locked_snapshot(
        school_year_id=int(school_year_id),
        level_code=level,
        batch_fingerprint=current_fp,
        actor=actor,
        candidate_count=len(candidates),
    )

    # Backup không được phép làm thay đổi nguồn.
    if _preview_database_state_fingerprint() != preflight_db_fingerprint:
        raise SchoolMergerLevelBatchError(
            "Database thay đổi trong lúc tạo backup. Hệ thống chưa bắt đầu transaction ghi."
        )

    # ------------------------------------------------------------------
    # GIAI ĐOẠN 2 - MỘT WRITE TRANSACTION, KHÔNG MỞ PREVIEW CONNECTION KHÁC
    # ------------------------------------------------------------------
    con = engine._connect(read_only=False)
    committed = False
    batch_id: int | None = None
    final_summary: dict[str, Any] = {}

    try:
        con.execute("BEGIN IMMEDIATE")

        # Khi đã lấy write lock, không writer khác có thể chen vào.
        # Nếu fingerprint khác preflight thì dừng trước khi chạm dữ liệu nghiệp vụ.
        if _preview_database_state_fingerprint() != preflight_db_fingerprint:
            raise SchoolMergerLevelBatchError(
                "Database đã thay đổi giữa preflight và thời điểm lấy write lock. "
                "Transaction đã được rollback; hãy kiểm tra lại."
            )

        _ensure_tables(con)
        existing_batch = con.execute(
            f"SELECT id FROM {BATCH_TABLE} WHERE school_year_id=? AND level_code=? LIMIT 1",
            (int(school_year_id), level),
        ).fetchone()
        if existing_batch is not None:
            raise SchoolMergerLevelBatchError(
                "Cấp học này đã có nhật ký sáp nhập toàn cấp; không được chạy lần hai."
            )

        previous_year_id = engine._previous_year_id(con, int(school_year_id))
        actor_id = _safe_int(actor.get("id"))
        now_text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        operation_results: list[dict[str, Any]] = []

        for item in candidates:
            pid = str(item.get("plan_id") or "")
            detail = detail_by_plan[pid]

            target_id = _safe_int((detail.get("target_school") or {}).get("id"))
            source_ids = sorted(
                set(
                    int(x.get("id"))
                    for x in (detail.get("source_schools") or [])
                    if _safe_int((x or {}).get("id")) is not None
                )
            )
            if target_id is None or not source_ids:
                raise SchoolMergerLevelBatchError(f"Phương án {pid}: thiếu trường nguồn hoặc trường đích.")

            # Revalidate trực tiếp trên CHÍNH connection đang giữ write lock.
            _checked_target, _checked_sources, selection_blockers, _selection_warnings = engine._validate_selection(
                con,
                selected_year_id=int(school_year_id),
                target_school_id=target_id,
                source_ids=source_ids,
                require_active_sources=True,
            )
            if selection_blockers:
                raise SchoolMergerLevelBatchError(
                    f"Phương án {pid}: trạng thái trường thay đổi trong transaction: "
                    + " | ".join(str(x) for x in selection_blockers)
                )

            if _already_done_locked(
                con,
                plan_id=pid,
                school_year_id=int(school_year_id),
                target_school_id=target_id,
                source_ids=source_ids,
            ):
                raise SchoolMergerLevelBatchError(
                    f"Phương án {pid} đã có nhật ký thực hiện; dừng toàn cấp để tránh chạy lặp."
                )

            result = engine._apply_merge(
                con,
                selected_year_id=int(school_year_id),
                previous_year_id=previous_year_id,
                target_school_id=target_id,
                source_ids=source_ids,
                actor_user_id=actor_id,
                backup_name=backup_name,
                record_audit=False,
            )
            result.update(
                {
                    "official_plan_id": pid,
                    "batch_level_code": level,
                    "batch_fingerprint": current_fp,
                    "preview_fingerprint": str(detail.get("fingerprint") or ""),
                    "impact_state_fingerprint": str(detail.get("impact_state_fingerprint") or ""),
                    "source_audit_fingerprint": str((detail.get("source_audit") or {}).get("fingerprint") or ""),
                    "backup_name": backup_name,
                    "source_school_names": [
                        str(x.get("name") or x.get("excel_name") or "")
                        for x in (detail.get("source_schools") or [])
                    ],
                    "target_school_name": str(
                        (detail.get("target_school") or {}).get("name")
                        or (detail.get("target_school") or {}).get("excel_name")
                        or ""
                    ),
                }
            )
            summary_json = json.dumps(result, ensure_ascii=False, default=str)

            cur = con.execute(
                "INSERT INTO school_merger_operations ("
                "school_year_id,target_school_id,source_school_ids_json,actor_user_id,"
                "backup_name,summary_json,created_at) VALUES (?,?,?,?,?,?,?)",
                (
                    int(school_year_id),
                    target_id,
                    json.dumps(source_ids, ensure_ascii=False),
                    actor_id,
                    backup_name,
                    summary_json,
                    now_text,
                ),
            )
            operation_id = int(cur.lastrowid)

            con.execute(
                f"INSERT INTO {OFFICIAL_EXECUTION_TABLE} ("
                "plan_id,operation_id,school_year_id,target_school_id,source_school_ids_json,"
                "actor_user_id,actor_username,actor_full_name,backup_name,preview_fingerprint,"
                "summary_json,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    pid,
                    operation_id,
                    int(school_year_id),
                    target_id,
                    json.dumps(source_ids, ensure_ascii=False),
                    actor_id,
                    str(actor.get("username") or ""),
                    str(actor.get("full_name") or ""),
                    backup_name,
                    str(detail.get("fingerprint") or ""),
                    summary_json,
                    now_text,
                ),
            )

            operation_results.append(
                {
                    "plan_id": pid,
                    "operation_id": operation_id,
                    "sources": result.get("source_school_names") or [],
                    "target": result.get("target_school_name") or "",
                    "direct_rows": sum(int(x.get("rows") or 0) for x in (result.get("direct_moves") or [])),
                    "staff_rollover_created": int(result.get("staff_rollover_created") or 0),
                    "source_school_logins_disabled": int(result.get("source_school_logins_disabled") or 0),
                    "sources_deactivated": int(result.get("sources_deactivated") or 0),
                }
            )

        fk = con.execute("PRAGMA foreign_key_check").fetchall()
        integrity = str(con.execute("PRAGMA integrity_check").fetchone()[0])
        if fk or integrity.lower() != "ok":
            raise SchoolMergerLevelBatchError(
                f"Hậu kiểm toàn cấp trước COMMIT không đạt: integrity={integrity}; fk={len(fk)}"
            )

        final_summary = {
            "school_year_id": int(school_year_id),
            "qd3805_registry_schema": LEVEL_LOCK_SCHEMA,
            "qd3805_registry_fingerprint": str((preflight.get("registry") or {}).get("fingerprint") or ""),
            "school_year": preflight.get("school_year") or {},
            "level_code": level,
            "batch_fingerprint": current_fp,
            "backup_name": backup_name,
            "total_plans": int(preflight.get("total") or 0),
            "keep_count": int((preflight.get("counts") or {}).get("KEEP") or 0),
            "done_before_count": int((preflight.get("counts") or {}).get("DONE") or 0),
            "executed_count": len(operation_results),
            "operations": operation_results,
            "integrity": integrity,
            "foreign_key_errors": len(fk),
            "actor": {
                "id": actor.get("id"),
                "username": actor.get("username"),
                "full_name": actor.get("full_name"),
            },
            "created_at": now_text,
        }

        cur = con.execute(
            f"INSERT INTO {BATCH_TABLE} ("
            "school_year_id,level_code,actor_user_id,actor_username,actor_full_name,backup_name,"
            "batch_fingerprint,total_plans,keep_count,done_before_count,executed_count,summary_json,created_at"
            ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                int(school_year_id),
                level,
                actor_id,
                str(actor.get("username") or ""),
                str(actor.get("full_name") or ""),
                backup_name,
                current_fp,
                final_summary["total_plans"],
                final_summary["keep_count"],
                final_summary["done_before_count"],
                final_summary["executed_count"],
                json.dumps(final_summary, ensure_ascii=False, default=str),
                now_text,
            ),
        )
        batch_id = int(cur.lastrowid)
        final_summary["batch_id"] = batch_id

        con.execute(
            f"UPDATE {BATCH_TABLE} SET summary_json=? WHERE id=?",
            (json.dumps(final_summary, ensure_ascii=False, default=str), batch_id),
        )

        con.commit()
        committed = True

        if backup_dir is not None:
            (backup_dir / "ket_qua_sap_nhap_toan_cap.json").write_text(
                json.dumps(
                    {"status": "COMMITTED", **final_summary},
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                ),
                encoding="utf-8",
            )
        return final_summary

    except Exception as exc:
        if not committed:
            try:
                con.rollback()
            except Exception:
                pass
        if backup_dir is not None:
            try:
                (backup_dir / "ket_qua_sap_nhap_toan_cap.json").write_text(
                    json.dumps(
                        {
                            "status": "ROLLED_BACK",
                            "school_year_id": int(school_year_id),
                            "level_code": level,
                            "error": str(exc),
                        },
                        ensure_ascii=False,
                        indent=2,
                        default=str,
                    ),
                    encoding="utf-8",
                )
            except Exception:
                pass
        if isinstance(exc, SchoolMergerLevelBatchError):
            raise
        raise SchoolMergerLevelBatchError(str(exc)) from exc
    finally:
        con.close()


def get_level_batch_result(batch_id: int) -> dict[str, Any] | None:
    con = engine._connect(read_only=True)
    try:
        if not engine._table_exists(con, BATCH_TABLE):
            return None
        row = con.execute(f"SELECT * FROM {BATCH_TABLE} WHERE id=? LIMIT 1", (int(batch_id),)).fetchone()
        if row is None:
            return None
        data = dict(row)
        try:
            summary = json.loads(data.get("summary_json") or "{}")
        except Exception:
            summary = {}
        data["summary"] = summary
        return data
    finally:
        con.close()
