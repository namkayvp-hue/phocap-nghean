from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from app.services import school_merger_service as engine
from app.services.school_merger_preview_service import (
    _category,
    _database_state_fingerprint,
    _impact_state_fingerprint,
    _table_label,
)
from app.services.school_merger_source_audit_service import (
    SchoolMergerSourceAuditError,
    audit_official_plan_source,
)


class SchoolMergerFutureError(RuntimeError):
    pass


FUTURE_CONFIRM_PHRASE = "SAP NHAP"
FUTURE_EXECUTION_TABLE = "school_merger_future_executions"
EXPORT_DIR = Path(engine.PROJECT_DIR) / "exports"


def _safe_int(value: Any) -> int | None:
    try:
        text = str(value or "").strip()
        return int(text) if text else None
    except (TypeError, ValueError):
        return None


def _normalize_level(value: Any) -> str:
    level = str(value or "").strip().upper()
    if level not in {"MN", "TH", "THCS", "THPT"}:
        raise SchoolMergerFutureError("Cấp học dùng để kiểm tra nguồn không hợp lệ.")
    return level



def _normalize_source_audit_ui_message(value: Any) -> str:
    """Chuẩn hóa thông báo kiểm tra nguồn để không lộ số phiên bản/ký hiệu nội bộ trên UI."""
    text = str(value or "")
    replacements = [
        ("kiểm tra nguồn V4.3", "kiểm tra dữ liệu nguồn"),
        ("Kiểm tra nguồn V4.3", "Kiểm tra dữ liệu nguồn"),
        ("V4.3", ""),
        ("V4.1", ""),
        ("blocker", "lỗi cần xử lý"),
        ("BLOCKER", "LỖI CẦN XỬ LÝ"),
        ("DB đủ điều kiện rollover", "dữ liệu hệ thống đủ điều kiện kế thừa"),
        ("DB đủ rollover", "dữ liệu hệ thống đủ điều kiện kế thừa"),
        ("DB năm nguồn", "dữ liệu hệ thống năm nguồn"),
        ("rollover", "kế thừa"),
        ("staff_member_id", "mã nhân sự"),
        ("Database", "Cơ sở dữ liệu"),
        ("database", "cơ sở dữ liệu"),
        ("integrity_check", "kiểm tra toàn vẹn dữ liệu"),
        ("foreign_key_check", "kiểm tra liên kết dữ liệu"),
    ]
    for old, new in replacements:
        text = text.replace(old, new)
    return " ".join(text.split())

def _signature(*, school_year_id: int, level_code: str, target_school_id: int, source_ids: list[int]) -> str:
    stable = {
        "school_year_id": int(school_year_id),
        "level_code": _normalize_level(level_code),
        "target_school_id": int(target_school_id),
        "source_school_ids": sorted(set(int(x) for x in source_ids if int(x) != int(target_school_id))),
    }
    raw = json.dumps(stable, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "PS-" + hashlib.sha256(raw).hexdigest()[:20].upper()


def _school_payload(con: sqlite3.Connection, school_id: int, year_id: int) -> dict[str, Any] | None:
    row = engine._school_row(con, int(school_id))
    if row is None:
        return None
    item = dict(row)
    item["levels"] = sorted(engine._school_levels(con, int(school_id), int(year_id)))
    return item


def _build_synthetic_plan(
    con: sqlite3.Connection,
    *,
    school_year_id: int,
    level_code: str,
    target_school_id: int,
    source_ids: list[int],
) -> dict[str, Any]:
    level = _normalize_level(level_code)
    source_ids = sorted(set(int(x) for x in source_ids if int(x) != int(target_school_id)))
    years = [dict(x) for x in engine._school_year_rows(con)]
    year = next((x for x in years if int(x["id"]) == int(school_year_id)), None)
    if year is None:
        raise SchoolMergerFutureError("Không tìm thấy năm học được chọn.")
    target = _school_payload(con, int(target_school_id), int(school_year_id))
    if target is None:
        raise SchoolMergerFutureError("Không tìm thấy trường đích.")
    sources: list[dict[str, Any]] = []
    for sid in source_ids:
        school = _school_payload(con, int(sid), int(school_year_id))
        if school is None:
            raise SchoolMergerFutureError(f"Không tìm thấy trường nguồn id={sid}.")
        sources.append(school)

    sig = _signature(
        school_year_id=int(school_year_id),
        level_code=level,
        target_school_id=int(target_school_id),
        source_ids=source_ids,
    )
    return {
        "id": sig,
        "source_kind": "FUTURE_MANUAL",
        "action_type": "MAPPED",
        "match_status": "MATCHED",
        "school_year_id": int(school_year_id),
        "school_year_code": str(year.get("code") or year.get("name") or ""),
        "level_codes": [level],
        "commune_excel": str(target.get("commune_name") or ""),
        "target_school": target,
        "source_schools": sources,
        "plan_text": "Sáp nhập phát sinh – nguồn/đích tự chọn",
    }


def _ensure_future_table(con: sqlite3.Connection) -> None:
    con.execute(
        f"CREATE TABLE IF NOT EXISTS {FUTURE_EXECUTION_TABLE} ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "signature TEXT NOT NULL UNIQUE,"
        "school_year_id INTEGER NOT NULL,"
        "level_code TEXT NOT NULL,"
        "target_school_id INTEGER NOT NULL,"
        "source_school_ids_json TEXT NOT NULL,"
        "operation_id INTEGER,"
        "actor_user_id INTEGER,"
        "actor_username TEXT,"
        "actor_full_name TEXT,"
        "backup_name TEXT NOT NULL,"
        "impact_state_fingerprint TEXT NOT NULL,"
        "source_audit_fingerprint TEXT NOT NULL,"
        "summary_json TEXT NOT NULL,"
        "created_at DATETIME NOT NULL"
        ")"
    )


def _exact_operation(
    con: sqlite3.Connection,
    *,
    school_year_id: int,
    target_school_id: int,
    source_ids: list[int],
) -> dict[str, Any] | None:
    wanted = sorted(set(int(x) for x in source_ids))
    if engine._table_exists(con, FUTURE_EXECUTION_TABLE):
        rows = con.execute(
            f"SELECT * FROM {FUTURE_EXECUTION_TABLE} WHERE school_year_id=? AND target_school_id=? ORDER BY id DESC",
            (int(school_year_id), int(target_school_id)),
        ).fetchall()
        for row in rows:
            try:
                got = sorted(set(int(x) for x in json.loads(row["source_school_ids_json"] or "[]")))
            except Exception:
                continue
            if got == wanted:
                return dict(row)
    if not engine._table_exists(con, "school_merger_operations"):
        return None
    rows = con.execute(
        "SELECT * FROM school_merger_operations WHERE school_year_id=? AND target_school_id=? ORDER BY id DESC",
        (int(school_year_id), int(target_school_id)),
    ).fetchall()
    for row in rows:
        try:
            got = sorted(set(int(x) for x in json.loads(row["source_school_ids_json"] or "[]")))
        except Exception:
            continue
        if got == wanted:
            return dict(row)
    return None


def _year_codes(years: list[dict[str, Any]], ids: list[int]) -> list[str]:
    mapping = {int(x["id"]): str(x.get("code") or x.get("name") or x["id"]) for x in years}
    return [mapping.get(int(x), str(x)) for x in ids]


def build_future_preview(
    *,
    school_year_id: int,
    level_code: str,
    target_school_id: int,
    source_ids: list[int],
) -> dict[str, Any]:
    level = _normalize_level(level_code)
    source_ids = sorted(set(int(x) for x in source_ids if int(x) != int(target_school_id)))
    database_before = _database_state_fingerprint()
    blockers: list[str] = []
    warnings: list[str] = []
    source_audit: dict[str, Any] | None = None
    impact_fingerprint = ""
    impact_summary: dict[str, Any] = {}
    simulation_result: dict[str, Any] | None = None
    simulation_error = ""

    with engine._connect(read_only=True) as con:
        plan = _build_synthetic_plan(
            con,
            school_year_id=int(school_year_id),
            level_code=level,
            target_school_id=int(target_school_id),
            source_ids=source_ids,
        )
        target = dict(plan["target_school"])
        sources = [dict(x) for x in plan["source_schools"]]
        years = [dict(x) for x in engine._school_year_rows(con)]
        selected_year = next((x for x in years if int(x["id"]) == int(school_year_id)), None)
        previous_year_id = engine._previous_year_id(con, int(school_year_id))
        previous_year = next((x for x in years if previous_year_id is not None and int(x["id"]) == int(previous_year_id)), None)

        integrity = str(con.execute("PRAGMA integrity_check").fetchone()[0])
        fk = con.execute("PRAGMA foreign_key_check").fetchall()
        if integrity.lower() != "ok":
            blockers.append(f"Database không đạt integrity_check: {integrity}")
        if fk:
            blockers.append(f"Database đang có {len(fk)} lỗi foreign_key_check.")

        checked_target, checked_sources, selection_blockers, selection_warnings = engine._validate_selection(
            con,
            selected_year_id=int(school_year_id),
            target_school_id=int(target_school_id),
            source_ids=source_ids,
            require_active_sources=True,
        )
        blockers.extend(selection_blockers)
        warnings.extend(selection_warnings)

        involved = [checked_target or target, *(checked_sources or sources)]
        for school in involved:
            levels = set(str(x).upper() for x in (school.get("levels") or []))
            if level not in levels:
                blockers.append(
                    f"{school.get('name') or school.get('id')} không có cấp {level} trong năm học đã chọn; "
                    "không được dùng cho phương án phát sinh này."
                )

        completed = _exact_operation(
            con,
            school_year_id=int(school_year_id),
            target_school_id=int(target_school_id),
            source_ids=source_ids,
        )
        if completed is not None:
            blockers.append("Cùng nguồn → đích và năm hiệu lực đã có nhật ký sáp nhập; không được chạy lần hai.")

        try:
            source_audit = audit_official_plan_source(
                str(plan["id"]),
                con=con,
                plan=plan,
                previous_year_id=previous_year_id,
            )
        except (SchoolMergerSourceAuditError, sqlite3.Error) as exc:
            source_audit = {
                "status": "BLOCK",
                "pass": False,
                "fingerprint": "",
                "school_checks": [],
                "blockers": [str(exc)],
                "warnings": [],
                "message": "Không thể kiểm tra dữ liệu nguồn.",
            }
        # Chuẩn hóa thông báo chi tiết để giao diện không lộ mã lỗi nội bộ/thuật ngữ kỹ thuật.
        for school_check in source_audit.get("school_checks") or []:
            for issue in school_check.get("issues") or []:
                if isinstance(issue, dict) and issue.get("message") is not None:
                    issue["message"] = _normalize_source_audit_ui_message(issue.get("message"))

        if not source_audit.get("pass"):
            blockers.extend(["Kiểm tra dữ liệu nguồn – " + _normalize_source_audit_ui_message(x) for x in (source_audit.get("blockers") or ["Kiểm tra dữ liệu nguồn chưa đạt."])])
        warnings.extend(["Kiểm tra dữ liệu nguồn – " + _normalize_source_audit_ui_message(x) for x in (source_audit.get("warnings") or [])])

        inventory = engine._preview_inventory(
            con,
            selected_year_id=int(school_year_id),
            previous_year_id=previous_year_id,
            target_school_id=int(target_school_id),
            source_ids=source_ids,
        )
        blockers.extend(inventory.get("no_year_blockers") or [])
        if inventory.get("staff_previous_duplicates"):
            blockers.append(
                f"Đội ngũ năm trước có {inventory['staff_previous_duplicates']} staff_member_id trùng trong nhóm sáp nhập."
            )
        if inventory.get("staff_unclassified"):
            blockers.append(f"Có {inventory['staff_unclassified']} hồ sơ đội ngũ năm trước chưa phân loại được.")
        if previous_year_id is None and engine._table_exists(con, "staff_year_records"):
            blockers.append("Không xác định được năm học liền trước để khóa nguồn rollover đội ngũ.")
        if inventory.get("staff_existing_elsewhere"):
            warnings.append(
                f"Có {inventory['staff_existing_elsewhere']} nhân sự đã có hồ sơ năm hiện hành ở trường khác; engine sẽ giữ nguyên hồ sơ đó."
            )

        impact_fingerprint, impact_summary = _impact_state_fingerprint(
            con,
            plan=plan,
            selected_year_id=int(school_year_id),
            previous_year_id=previous_year_id,
            target_school_id=int(target_school_id),
            source_ids=source_ids,
        )

        direct_rows: list[dict[str, Any]] = []
        for row in inventory.get("direct_rows") or []:
            item = dict(row)
            table = str(item.get("table") or "")
            item["label"] = _table_label(table)
            item["category"] = _category(table)
            direct_rows.append(item)
        no_year_rows: list[dict[str, Any]] = []
        for row in inventory.get("no_year_rows") or []:
            item = dict(row)
            table = str(item.get("table") or "")
            item["label"] = _table_label(table)
            item["category"] = _category(table)
            no_year_rows.append(item)

        if not blockers:
            mem: sqlite3.Connection | None = None
            try:
                mem = sqlite3.connect(":memory:")
                mem.row_factory = sqlite3.Row
                con.backup(mem)
                mem.execute("PRAGMA foreign_keys=ON")
                mem.execute("BEGIN")
                simulation_result = engine._apply_merge(
                    mem,
                    selected_year_id=int(school_year_id),
                    previous_year_id=previous_year_id,
                    target_school_id=int(target_school_id),
                    source_ids=source_ids,
                    actor_user_id=None,
                    record_audit=False,
                )
                mem.rollback()
            except Exception as exc:
                simulation_error = str(exc)
                blockers.append("Mô phỏng kỹ thuật trên bản sao RAM thất bại: " + simulation_error)
                if mem is not None:
                    try:
                        mem.rollback()
                    except Exception:
                        pass
            finally:
                if mem is not None:
                    mem.close()

    database_after = _database_state_fingerprint()
    if database_before != database_after:
        blockers.append("Database đã thay đổi trong lúc lập bản xem trước; hãy tải lại để lấy bản xem trước ổn định.")

    direct_move_total = sum(int(x.get("current_year_rows") or 0) for x in direct_rows)
    no_year_move_total = sum(int(x.get("move_rows") or 0) for x in no_year_rows)
    historical_total = int(inventory.get("historical_total") or 0) + sum(int(x.get("preserve_rows") or 0) for x in no_year_rows)

    return {
        "plan": plan,
        "signature": str(plan["id"]),
        "school_year": selected_year,
        "previous_year": previous_year,
        "level_code": level,
        "target_school": checked_target or target,
        "source_schools": checked_sources or sources,
        "move_year_codes": _year_codes(years, list(inventory.get("move_year_ids") or [])),
        "past_year_codes": _year_codes(years, list(inventory.get("past_year_ids") or [])),
        "inventory": inventory,
        "direct_rows": direct_rows,
        "no_year_rows": no_year_rows,
        "summary": {
            "direct_move_rows": direct_move_total,
            "no_year_move_rows": no_year_move_total,
            "historical_preserve_rows": historical_total,
            "users_move_target": int(inventory.get("users_move_target") or 0),
            "source_school_logins_disable": int(inventory.get("source_school_logins_disable") or 0),
            "staff_rollover_candidates": int(inventory.get("staff_rollover_candidates") or 0),
            "sources_deactivate": len(source_ids),
        },
        "warnings": warnings,
        "blockers": blockers,
        "completed_operation": completed,
        "source_audit": source_audit,
        "v43_source_check_ok": bool(source_audit and source_audit.get("pass")),
        "impact_state_fingerprint": impact_fingerprint,
        "impact_state_summary": impact_summary,
        "v41_state_check_ok": bool(impact_fingerprint) and not blockers and simulation_result is not None,
        "simulation_result": simulation_result,
        "simulation_error": simulation_error,
        "simulation_ok": not blockers and simulation_result is not None,
        "safe_for_execution": not blockers and simulation_result is not None,
        "database_fingerprint": database_after,
        "confirm_phrase": FUTURE_CONFIRM_PHRASE,
        "rules": [
            "Trường đích giữ nguyên school_id.",
            "Trường nguồn không bị xóa; chỉ chuyển inactive/đã sáp nhập sau khi COMMIT thành công.",
            "Dữ liệu trước năm hiệu lực giữ nguyên tại trường cũ; CURRENT/FUTURE đi theo trường đích.",
            "Nguồn và đích có thể khác xã/phường; dữ liệu CURRENT/FUTURE sẽ dùng commune_id của trường đích.",
            "Cấp kiểm tra nguồn phải tồn tại ở cả nguồn và đích trong năm hiệu lực.",
            "Kiểm tra dữ liệu nguồn + trạng thái bản xem trước + mô phỏng RAM đều phải đạt trước khi mở thực hiện.",
            "Backend tính lại cả hai fingerprint sau BEGIN IMMEDIATE; lệch là chặn ghi.",
            "Backup tự động, một transaction, integrity_check + foreign_key_check trước COMMIT, chống chạy lặp.",
        ],
    }


def _safe_folder_piece(value: Any) -> str:
    text = re.sub(r"[^A-Za-z0-9_-]+", "_", str(value or "").strip())
    return text[:60] or "future"


def _backup_locked_snapshot(
    *,
    signature: str,
    school_year_id: int,
    level_code: str,
    target_school_id: int,
    source_ids: list[int],
    actor: dict[str, Any],
) -> tuple[Path, str]:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    folder = EXPORT_DIR / f"backup_truoc_sap_nhap_phat_sinh_{stamp}_{_safe_folder_piece(signature)}"
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
        chk.execute("PRAGMA foreign_keys=ON")
        integrity = str(chk.execute("PRAGMA integrity_check").fetchone()[0])
        fk = chk.execute("PRAGMA foreign_key_check").fetchall()
        if integrity.lower() != "ok" or fk:
            raise SchoolMergerFutureError(
                f"Backup trước sáp nhập không đạt: integrity={integrity}; foreign_key_check={len(fk)}"
            )
    finally:
        chk.close()

    meta = {
        "backup_type": "automatic_before_future_school_merger_v45",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "signature": signature,
        "school_year_id": int(school_year_id),
        "level_code": level_code,
        "target_school_id": int(target_school_id),
        "source_school_ids": sorted(set(int(x) for x in source_ids)),
        "actor": {
            "id": actor.get("id"),
            "username": actor.get("username"),
            "full_name": actor.get("full_name"),
            "role_code": actor.get("role_code"),
        },
        "database_backup": str(db_target),
    }
    (folder / "thong_tin_sap_nhap_phat_sinh_v45.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    return folder, folder.name


def execute_future_merge(
    *,
    school_year_id: int,
    level_code: str,
    target_school_id: int,
    source_ids: list[int],
    actor: dict[str, Any],
    expected_impact_state_fingerprint: str,
    expected_source_audit_fingerprint: str,
    confirmation_scope: str,
    confirmation_text: str,
) -> dict[str, Any]:
    if str(confirmation_scope or "").strip().lower() != "yes":
        raise SchoolMergerFutureError("Bạn chưa tích xác nhận đã kiểm tra đúng nguồn, đích và năm hiệu lực.")
    if str(confirmation_text or "").strip().upper() != FUTURE_CONFIRM_PHRASE:
        raise SchoolMergerFutureError(f"Câu xác nhận chưa đúng. Hãy nhập chính xác: {FUTURE_CONFIRM_PHRASE}")
    if not str(expected_impact_state_fingerprint or "").strip():
        raise SchoolMergerFutureError("Thiếu dấu vân tay dữ liệu tác động; hãy XEM TRƯỚC lại.")
    if not str(expected_source_audit_fingerprint or "").strip():
        raise SchoolMergerFutureError("Thiếu dấu vân tay nguồn đối chiếu; hãy XEM TRƯỚC lại.")

    source_ids = sorted(set(int(x) for x in source_ids if int(x) != int(target_school_id)))
    level = _normalize_level(level_code)
    signature = _signature(
        school_year_id=int(school_year_id), level_code=level,
        target_school_id=int(target_school_id), source_ids=source_ids,
    )

    con = engine._connect(read_only=False)
    committed = False
    backup_name = ""
    try:
        con.execute("BEGIN IMMEDIATE")
        preview = build_future_preview(
            school_year_id=int(school_year_id),
            level_code=level,
            target_school_id=int(target_school_id),
            source_ids=source_ids,
        )
        if not preview.get("safe_for_execution") or not preview.get("simulation_ok"):
            raise SchoolMergerFutureError(
                "Phương án phát sinh không còn đạt cổng an toàn: " + " | ".join(preview.get("blockers") or [])
            )
        current_source_fp = str((preview.get("source_audit") or {}).get("fingerprint") or "")
        current_impact_fp = str(preview.get("impact_state_fingerprint") or "")
        if current_source_fp != str(expected_source_audit_fingerprint):
            raise SchoolMergerFutureError(
                "Nguồn đối chiếu đã thay đổi từ lúc xem trước; hệ thống chặn ghi. Hãy XEM TRƯỚC lại."
            )
        if current_impact_fp != str(expected_impact_state_fingerprint):
            raise SchoolMergerFutureError(
                "Dữ liệu thuộc phạm vi sáp nhập đã thay đổi từ lúc xem trước; hệ thống chặn ghi. Hãy XEM TRƯỚC lại."
            )

        _ensure_future_table(con)
        if con.execute(f"SELECT 1 FROM {FUTURE_EXECUTION_TABLE} WHERE signature=? LIMIT 1", (signature,)).fetchone():
            raise SchoolMergerFutureError("Phương án phát sinh này đã có nhật ký; không được thực hiện lần hai.")
        if _exact_operation(
            con,
            school_year_id=int(school_year_id),
            target_school_id=int(target_school_id),
            source_ids=source_ids,
        ) is not None:
            raise SchoolMergerFutureError("Cùng nguồn → đích và năm hiệu lực đã có nhật ký sáp nhập; không được chạy lại.")

        _, backup_name = _backup_locked_snapshot(
            signature=signature,
            school_year_id=int(school_year_id),
            level_code=level,
            target_school_id=int(target_school_id),
            source_ids=source_ids,
            actor=actor,
        )

        previous_year_id = engine._previous_year_id(con, int(school_year_id))
        result = engine._apply_merge(
            con,
            selected_year_id=int(school_year_id),
            previous_year_id=previous_year_id,
            target_school_id=int(target_school_id),
            source_ids=source_ids,
            actor_user_id=int(actor["id"]) if actor.get("id") is not None else None,
            backup_name=backup_name,
            record_audit=True,
        )
        operation_id = int(con.execute("SELECT last_insert_rowid()").fetchone()[0])

        integrity = str(con.execute("PRAGMA integrity_check").fetchone()[0])
        fk = con.execute("PRAGMA foreign_key_check").fetchall()
        if integrity.lower() != "ok" or fk:
            raise SchoolMergerFutureError(
                f"Hậu kiểm trước COMMIT không đạt: integrity={integrity}; foreign_key_check={len(fk)}"
            )

        summary = dict(result)
        summary["impact_state_fingerprint"] = current_impact_fp
        summary["source_audit_fingerprint"] = current_source_fp
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        con.execute(
            f"INSERT INTO {FUTURE_EXECUTION_TABLE} ("
            "signature,school_year_id,level_code,target_school_id,source_school_ids_json,operation_id,"
            "actor_user_id,actor_username,actor_full_name,backup_name,impact_state_fingerprint,"
            "source_audit_fingerprint,summary_json,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                signature,
                int(school_year_id),
                level,
                int(target_school_id),
                json.dumps(source_ids, ensure_ascii=False),
                operation_id,
                int(actor["id"]) if actor.get("id") is not None else None,
                str(actor.get("username") or ""),
                str(actor.get("full_name") or ""),
                backup_name,
                current_impact_fp,
                current_source_fp,
                json.dumps(summary, ensure_ascii=False, default=str),
                created_at,
            ),
        )
        execution_id = int(con.execute("SELECT last_insert_rowid()").fetchone()[0])
        con.commit()
        committed = True
    except Exception:
        if not committed:
            try:
                con.rollback()
            except Exception:
                pass
        raise
    finally:
        con.close()

    return {
        "execution_id": execution_id,
        "signature": signature,
        "operation_id": operation_id,
        "backup_name": backup_name,
        "summary": summary,
    }


def get_future_execution_result(execution_id: int) -> dict[str, Any] | None:
    with engine._connect(read_only=True) as con:
        if not engine._table_exists(con, FUTURE_EXECUTION_TABLE):
            return None
        row = con.execute(f"SELECT * FROM {FUTURE_EXECUTION_TABLE} WHERE id=? LIMIT 1", (int(execution_id),)).fetchone()
        if row is None:
            return None
        item = dict(row)
        try:
            source_ids = [int(x) for x in json.loads(item.get("source_school_ids_json") or "[]")]
        except Exception:
            source_ids = []
        try:
            summary = json.loads(item.get("summary_json") or "{}")
        except Exception:
            summary = {}
        target = _school_payload(con, int(item["target_school_id"]), int(item["school_year_id"]))
        sources = [x for sid in source_ids if (x := _school_payload(con, sid, int(item["school_year_id"]))) is not None]
        year = next((dict(x) for x in engine._school_year_rows(con) if int(x["id"]) == int(item["school_year_id"])), None)
        item.update({
            "source_school_ids": source_ids,
            "summary": summary,
            "target_school": target,
            "source_schools": sources,
            "school_year": year,
        })
        return item


def list_future_executions(limit: int = 50) -> list[dict[str, Any]]:
    with engine._connect(read_only=True) as con:
        if not engine._table_exists(con, FUTURE_EXECUTION_TABLE):
            return []
        rows = con.execute(
            f"SELECT * FROM {FUTURE_EXECUTION_TABLE} ORDER BY id DESC LIMIT ?", (max(1, min(int(limit), 200)),)
        ).fetchall()
        return [dict(x) for x in rows]
