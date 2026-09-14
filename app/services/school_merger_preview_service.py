from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from app.services.school_merger_official_registry import list_official_registry_plans
from app.services import school_merger_service as engine
from app.services.school_merger_source_audit_service import (
    SchoolMergerSourceAuditError,
    audit_official_plan_source,
)


class SchoolMergerPreviewError(RuntimeError):
    pass


TABLE_LABELS = {
    "classes": "Lớp học",
    "student_enrollments": "Học sinh / ghi danh",
    "staff_year_records": "Đội ngũ",
    "school_network_year_data": "Mạng lưới trường học",
    "school_facility_year_items": "Cơ sở vật chất",
    "school_site_year_records": "Điểm trường",
    "school_staff_year_summaries": "Tổng hợp đội ngũ",
    "school_structured_report_inputs": "Dữ liệu báo cáo cấu trúc",
    "school_mn01_gv_inputs": "Dữ liệu MN-01-GV",
    "school_mn01_csvc_inputs": "Dữ liệu MN-01-CSVC",
    "finance_year_entries": "Tài chính",
    "survey_person_year_records": "Điều tra – dữ liệu người theo năm",
    "survey_execution_workflow_logs": "Điều tra – nhật ký quy trình",
    "survey_investigation_participants": "Điều tra – người tham gia",
    "survey_investigation_team_members": "Điều tra – thành viên tổ",
    "survey_participant_submissions": "Điều tra – gửi danh sách",
    "survey_school_assignments": "Điều tra – phân công trường",
    "survey_team_registration_logs": "Điều tra – nhật ký đăng ký tổ",
    "account_provision_batch_items": "Cấp tài khoản",
}


def _table_label(table: str) -> str:
    if table in TABLE_LABELS:
        return TABLE_LABELS[table]
    if table.startswith("survey_"):
        return "Điều tra – " + table.removeprefix("survey_").replace("_", " ")
    if table.startswith("school_"):
        return "Dữ liệu trường – " + table.removeprefix("school_").replace("_", " ")
    return table.replace("_", " ")


def _category(table: str) -> str:
    if table == "classes":
        return "Lớp học"
    if table == "student_enrollments":
        return "Học sinh"
    if table == "staff_year_records" or "staff" in table:
        return "Đội ngũ"
    if table.startswith("survey_"):
        return "Điều tra"
    if table == "users" or "account" in table:
        return "Tài khoản"
    return "Dữ liệu nghiệp vụ"


def _year_code(value: Any) -> str:
    return str(value or "").replace("–", "-").replace("—", "-").strip()


def _find_official_plan(plan_id: str) -> dict[str, Any]:
    wanted = str(plan_id or "").strip()
    if not wanted:
        raise SchoolMergerPreviewError("Thiếu mã phương án chính thức.")
    for plan in list_official_registry_plans(display_mode="all"):
        if str(plan.get("id") or "") == wanted:
            return plan
    raise SchoolMergerPreviewError(f"Không tìm thấy phương án chính thức: {wanted}")


def _already_executed(
    con: sqlite3.Connection,
    *,
    plan_id: str,
    school_year_id: int,
    target_school_id: int,
    source_ids: list[int],
) -> dict[str, Any] | None:
    if engine._table_exists(con, "school_merger_official_executions"):
        row = con.execute(
            "SELECT id,plan_id,operation_id,school_year_id,target_school_id,"
            "source_school_ids_json,backup_name,created_at "
            "FROM school_merger_official_executions WHERE plan_id=? LIMIT 1",
            (str(plan_id),),
        ).fetchone()
        if row is not None:
            return dict(row)

    if not engine._table_exists(con, "school_merger_operations"):
        return None
    rows = con.execute(
        "SELECT id,school_year_id,target_school_id,source_school_ids_json,backup_name,created_at "
        "FROM school_merger_operations WHERE school_year_id=? AND target_school_id=? "
        "ORDER BY id DESC",
        (int(school_year_id), int(target_school_id)),
    ).fetchall()
    wanted = sorted(set(int(x) for x in source_ids))
    for row in rows:
        try:
            got = sorted(set(int(x) for x in json.loads(row["source_school_ids_json"] or "[]")))
        except Exception:
            continue
        if got == wanted:
            return dict(row)
    return None


def _sha256_path(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _database_state_fingerprint() -> str:
    """Dấu vân tay vật lý của SQLite main DB + WAL (nếu có).

    Không đưa file -shm vào vì nội dung khóa đọc/ghi có thể thay đổi chỉ do kết nối,
    dù dữ liệu logic không đổi. Từ V4.1 dấu này chỉ dùng để phát hiện DB thay đổi ngay
    trong lúc dựng một bản xem trước; cổng thực hiện dùng impact_state_fingerprint logic.
    """
    db_path = Path(engine.DATABASE_PATH)
    h = hashlib.sha256()
    for suffix in ("", "-wal"):
        path = Path(str(db_path) + suffix)
        h.update(suffix.encode("utf-8"))
        if not path.exists():
            h.update(b"MISSING")
            continue
        h.update(str(path.stat().st_size).encode("ascii"))
        h.update(_sha256_path(path).encode("ascii"))
    return h.hexdigest()


def _canonical_value(value: Any) -> Any:
    if isinstance(value, (bytes, bytearray, memoryview)):
        raw = bytes(value)
        return {"__bytes_len__": len(raw), "__bytes_sha256__": hashlib.sha256(raw).hexdigest()}
    if isinstance(value, float):
        return {"__float__": repr(value)}
    return value


def _canonical_row(row: sqlite3.Row | dict[str, Any]) -> str:
    data = dict(row)
    normalized = {str(k): _canonical_value(v) for k, v in data.items()}
    return json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _rows_component(
    con: sqlite3.Connection,
    *,
    table: str,
    where_sql: str = "",
    params: list[Any] | tuple[Any, ...] = (),
    rows_override: list[sqlite3.Row] | None = None,
) -> dict[str, Any]:
    if rows_override is None:
        sql = f"SELECT * FROM {engine._quote_ident(table)}"
        if where_sql:
            sql += " WHERE " + where_sql
        rows = con.execute(sql, params).fetchall()
    else:
        rows = list(rows_override)

    encoded = sorted(_canonical_row(row) for row in rows)
    h = hashlib.sha256()
    for item in encoded:
        h.update(item.encode("utf-8"))
        h.update(b"\n")

    schema_row = con.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    schema_sql = str(schema_row[0] or "") if schema_row is not None else ""
    schema_sha = hashlib.sha256(schema_sql.encode("utf-8")).hexdigest()
    return {
        "table": table,
        "rows": len(encoded),
        "rows_sha256": h.hexdigest(),
        "schema_sha256": schema_sha,
    }


def _impact_state_fingerprint(
    con: sqlite3.Connection,
    *,
    plan: dict[str, Any],
    selected_year_id: int,
    previous_year_id: int | None,
    target_school_id: int,
    source_ids: list[int],
) -> tuple[str, dict[str, Any]]:
    """V4.1: khóa đúng trạng thái LOGIC của tập dữ liệu có thể ảnh hưởng đến phép sáp nhập.

    Không dùng hash vật lý toàn file DB để quyết định bản xem trước còn hiệu lực. Vì vậy một
    thay đổi không liên quan ở đơn vị khác không làm vô hiệu bản xem trước; nhưng thay đổi ở
    trường nguồn/đích, dữ liệu CURRENT/FUTURE, rollover đội ngũ, tài khoản hoặc bảng gián tiếp
    liên quan sẽ làm đổi fingerprint và backend bắt buộc XEM TRƯỚC lại.
    """
    source_ids = sorted(set(int(x) for x in source_ids))
    involved_ids = sorted(set(source_ids + [int(target_school_id)]))
    move_year_ids, _ = engine._year_scope_ids(con, int(selected_year_id))
    move_year_set = set(int(x) for x in move_year_ids)

    components: list[dict[str, Any]] = []

    # Metadata năm học quyết định CURRENT/FUTURE và năm liền trước dùng cho rollover.
    years_payload = [_canonical_row(row) for row in engine._school_year_rows(con)]
    years_payload.sort()
    years_sha = hashlib.sha256("\n".join(years_payload).encode("utf-8")).hexdigest()
    components.append({"table": "__school_year_scope__", "rows": len(years_payload), "rows_sha256": years_sha, "schema_sha256": ""})

    # Trạng thái trường nguồn/đích (đặc biệt is_active, commune, mã/tên).
    if engine._table_exists(con, "schools"):
        components.append(_rows_component(
            con, table="schools",
            where_sql=f"id IN ({engine._markers(len(involved_ids))})",
            params=involved_ids,
        ))

    # Các bảng có school_year_id: nguồn sẽ chuyển + dữ liệu đích cùng phạm vi để phát hiện xung đột.
    for table in sorted(engine._current_year_tables(con)):
        cs = engine._column_names(con, table)
        if "school_id" not in cs or "school_year_id" not in cs:
            continue
        components.append(_rows_component(
            con, table=table,
            where_sql=(
                f"school_id IN ({engine._markers(len(involved_ids))}) "
                f"AND school_year_id IN ({engine._markers(len(move_year_ids))})"
            ),
            params=[*involved_ids, *move_year_ids],
        ))

    # Rollover đội ngũ còn phụ thuộc hồ sơ năm liền trước và hồ sơ năm hiện hành của cùng nhân sự ở nơi khác.
    if previous_year_id is not None and engine._table_exists(con, "staff_year_records"):
        previous_rows = con.execute(
            f"SELECT * FROM staff_year_records WHERE school_year_id=? "
            f"AND school_id IN ({engine._markers(len(involved_ids))})",
            [int(previous_year_id), *involved_ids],
        ).fetchall()
        components.append(_rows_component(
            con, table="staff_year_records", rows_override=previous_rows,
        ) | {"scope": "previous_year_rollover_sources"})
        staff_ids = sorted({int(r["staff_member_id"]) for r in previous_rows if r["staff_member_id"] is not None})
        if staff_ids:
            current_staff_rows = con.execute(
                f"SELECT * FROM staff_year_records WHERE school_year_id=? "
                f"AND staff_member_id IN ({engine._markers(len(staff_ids))})",
                [int(selected_year_id), *staff_ids],
            ).fetchall()
            components.append(_rows_component(
                con, table="staff_year_records", rows_override=current_staff_rows,
            ) | {"scope": "current_year_existing_staff_any_school"})

    # Tài khoản nguồn/đích quyết định chuyển tài khoản thường, khóa tài khoản trường nguồn và cổng đích.
    if engine._table_exists(con, "users"):
        components.append(_rows_component(
            con, table="users",
            where_sql=f"school_id IN ({engine._markers(len(involved_ids))})",
            params=involved_ids,
        ))

    # Bảng không có school_year_id: chỉ khóa các dòng nguồn có thể chuyển/chưa truy được năm;
    # đồng thời khóa các dòng tại đích để phát hiện thay đổi có thể gây UNIQUE/conflict.
    for table in sorted(engine._no_year_school_tables(con)):
        if table == "users" or table in engine.AUDIT_NO_YEAR_TABLES or table.endswith("_logs"):
            continue
        source_rows = con.execute(
            f"SELECT * FROM {engine._quote_ident(table)} "
            f"WHERE school_id IN ({engine._markers(len(source_ids))})",
            source_ids,
        ).fetchall() if source_ids else []
        relevant_source_rows: list[sqlite3.Row] = []
        for row in source_rows:
            year_id, _ = engine._resolve_indirect_year(con, table, row)
            if year_id is None or int(year_id) in move_year_set:
                relevant_source_rows.append(row)
        target_rows = con.execute(
            f"SELECT * FROM {engine._quote_ident(table)} WHERE school_id=?",
            (int(target_school_id),),
        ).fetchall()
        components.append(_rows_component(
            con, table=table, rows_override=[*relevant_source_rows, *target_rows],
        ) | {"scope": "indirect_current_future_source_plus_target"})

    # Nhật ký phép sáp nhập tương ứng: nếu có ai thực hiện phương án trong lúc chờ, trạng thái đổi ngay.
    if engine._table_exists(con, "school_merger_official_executions"):
        components.append(_rows_component(
            con, table="school_merger_official_executions",
            where_sql="plan_id=?", params=(str(plan.get("id") or ""),),
        ))
    if engine._table_exists(con, "school_merger_operations"):
        op_rows = con.execute(
            "SELECT * FROM school_merger_operations WHERE school_year_id=? AND target_school_id=? ORDER BY id",
            (int(selected_year_id), int(target_school_id)),
        ).fetchall()
        wanted = source_ids
        exact_rows: list[sqlite3.Row] = []
        for row in op_rows:
            try:
                got = sorted(set(int(x) for x in json.loads(row["source_school_ids_json"] or "[]")))
            except Exception:
                continue
            if got == wanted:
                exact_rows.append(row)
        components.append(_rows_component(
            con, table="school_merger_operations", rows_override=exact_rows,
        ) | {"scope": "same_source_target_operation"})

    plan_state = {
        "id": plan.get("id"),
        "action_type": plan.get("action_type"),
        "school_year_id": plan.get("school_year_id"),
        "school_year_code": plan.get("school_year_code"),
        "commune_id": plan.get("commune_id"),
        "commune_excel": plan.get("commune_excel"),
        "level_codes": plan.get("level_codes"),
        "target_school": plan.get("target_school"),
        "source_schools": plan.get("source_schools"),
        "target_excel": plan.get("target_excel"),
        "source_excel": plan.get("source_excel"),
    }
    stable = {
        "version": "V4.1-impact-state-1",
        "plan": plan_state,
        "selected_year_id": int(selected_year_id),
        "previous_year_id": int(previous_year_id) if previous_year_id is not None else None,
        "target_school_id": int(target_school_id),
        "source_ids": source_ids,
        "components": components,
    }
    raw = json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    total_rows = sum(int(c.get("rows") or 0) for c in components)
    summary = {
        "version": "V4.1-impact-state-1",
        "tables_or_scopes": len(components),
        "rows_hashed": total_rows,
    }
    return hashlib.sha256(raw).hexdigest(), summary


def _fingerprint(preview: dict[str, Any]) -> str:
    stable = {
        "plan_id": preview.get("plan", {}).get("id"),
        "school_year_id": preview.get("school_year", {}).get("id"),
        "target_school_id": preview.get("target_school", {}).get("id"),
        "source_school_ids": [x.get("id") for x in preview.get("source_schools", [])],
        "inventory": preview.get("inventory"),
        "simulation_result": preview.get("simulation_result"),
        "blockers": preview.get("blockers"),
        "warnings": preview.get("warnings"),
        "impact_state_fingerprint": preview.get("impact_state_fingerprint"),
        "source_audit_fingerprint": (preview.get("source_audit") or {}).get("fingerprint"),
    }
    raw = json.dumps(stable, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def build_official_plan_impact_preview(plan_id: str) -> dict[str, Any]:
    """V4.3: xem trước kỹ thuật + cổng dữ liệu nguồn; tuyệt đối chỉ đọc DB thật."""
    plan = _find_official_plan(plan_id)
    blockers: list[str] = []
    warnings: list[str] = []

    if str(plan.get("action_type") or "").upper() == "KEEP":
        return {
            "plan": plan,
            "keep_only": True,
            "blockers": [],
            "warnings": [],
            "safe_for_future_execution": False,
            "simulation_ok": True,
            "execution_enabled": False,
            "database_fingerprint": _database_state_fingerprint(),
            "source_audit": {"status": "NOT_APPLICABLE", "pass": True, "fingerprint": "", "school_checks": [], "blockers": [], "warnings": []},
            "v43_source_check_ok": True,
            "message": "Phương án GIỮ NGUYÊN: không có dữ liệu nào cần chuyển.",
        }

    if str(plan.get("action_type") or "").upper() != "MAPPED":
        blockers.append("Phương án đặc thù chưa xác định rõ trường nguồn và trường đích.")
    if str(plan.get("match_status") or "") != "MATCHED":
        blockers.append("Phương án chưa khớp đầy đủ tên trường với database.")

    target = dict(plan.get("target_school") or {})
    sources = [dict(x) for x in (plan.get("source_schools") or [])]
    if not target.get("id"):
        blockers.append("Không xác định được school_id của trường đích.")
    if not sources or any(not x.get("id") for x in sources):
        blockers.append("Không xác định đủ school_id của trường nguồn.")

    selected_year_id = plan.get("school_year_id")
    try:
        selected_year_id = int(selected_year_id) if selected_year_id is not None else None
    except (TypeError, ValueError):
        selected_year_id = None
    if selected_year_id is None:
        blockers.append("Không xác định được năm học hiệu lực của phương án.")

    if blockers:
        preview = {
            "plan": plan,
            "keep_only": False,
            "school_year": {"id": selected_year_id, "code": plan.get("school_year_code") or ""},
            "previous_year": None,
            "target_school": target,
            "source_schools": sources,
            "inventory": {},
            "direct_rows": [],
            "no_year_rows": [],
            "warnings": warnings,
            "blockers": blockers,
            "simulation_result": None,
            "simulation_error": "",
            "simulation_ok": False,
            "safe_for_future_execution": False,
            "execution_enabled": False,
            "database_fingerprint": _database_state_fingerprint(),
            "impact_state_fingerprint": "",
            "impact_state_summary": {},
            "v41_state_check_ok": False,
            "source_audit": None,
            "v43_source_check_ok": False,
        }
        preview["fingerprint"] = _fingerprint(preview)
        return preview

    target_id = int(target["id"])
    source_ids = sorted(set(int(x["id"]) for x in sources if int(x["id"]) != target_id))
    database_fingerprint_before = _database_state_fingerprint()

    with engine._connect(read_only=True) as con:
        integrity = str(con.execute("PRAGMA integrity_check").fetchone()[0])
        fk_errors = con.execute("PRAGMA foreign_key_check").fetchall()
        if integrity.lower() != "ok":
            blockers.append(f"Database không đạt integrity_check: {integrity}")
        if fk_errors:
            blockers.append(f"Database đang có {len(fk_errors)} lỗi foreign_key_check.")

        years = [dict(x) for x in engine._school_year_rows(con)]
        selected_year = next((x for x in years if int(x["id"]) == int(selected_year_id)), None)
        if selected_year is None:
            blockers.append("Năm học hiệu lực không tồn tại trong database.")
            selected_year = {"id": selected_year_id, "code": plan.get("school_year_code") or "", "name": ""}
        elif _year_code(selected_year.get("code")) != _year_code(plan.get("school_year_code")):
            blockers.append(
                "Năm học trong sổ phương án không khớp năm học trong database: "
                f"{plan.get('school_year_code')} / {selected_year.get('code')}"
            )

        previous_year_id = engine._previous_year_id(con, int(selected_year_id))
        previous_year = next(
            (x for x in years if previous_year_id is not None and int(x["id"]) == int(previous_year_id)),
            None,
        )

        # V4.3: cổng bắt buộc đối chiếu nguồn trước khi cho mô phỏng/thực hiện.
        try:
            source_audit = audit_official_plan_source(
                str(plan.get("id") or plan_id),
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
                "message": "Không thể kiểm tra dữ liệu nguồn V4.3.",
            }
        if not source_audit.get("pass"):
            blockers.extend([
                "V4.3 – " + str(x)
                for x in (source_audit.get("blockers") or ["Kiểm tra dữ liệu nguồn chưa đạt."])
            ])
        warnings.extend(["V4.3 – " + str(x) for x in (source_audit.get("warnings") or [])])

        checked_target, checked_sources, selection_blockers, selection_warnings = engine._validate_selection(
            con,
            selected_year_id=int(selected_year_id),
            target_school_id=target_id,
            source_ids=source_ids,
            require_active_sources=True,
        )
        blockers.extend(selection_blockers)
        warnings.extend(selection_warnings)

        completed = _already_executed(
            con,
            plan_id=str(plan.get("id") or ""),
            school_year_id=int(selected_year_id),
            target_school_id=target_id,
            source_ids=source_ids,
        )
        if completed:
            blockers.append(
                "Phương án này đã có nhật ký thực hiện trước đó; V4.1 không được phép thực hiện lần hai."
            )

        inventory = engine._preview_inventory(
            con,
            selected_year_id=int(selected_year_id),
            previous_year_id=previous_year_id,
            target_school_id=target_id,
            source_ids=source_ids,
        )
        blockers.extend(inventory.get("no_year_blockers") or [])
        if inventory.get("staff_previous_duplicates"):
            blockers.append(
                f"Đội ngũ năm trước có {inventory['staff_previous_duplicates']} staff_member_id trùng trong nhóm sáp nhập."
            )
        if inventory.get("staff_unclassified"):
            blockers.append(
                f"Có {inventory['staff_unclassified']} hồ sơ đội ngũ năm trước chưa phân loại được."
            )
        if previous_year_id is None and engine._table_exists(con, "staff_year_records"):
            warnings.append("Không xác định được năm học liền trước; chưa thể mô phỏng rollover đội ngũ.")
        if inventory.get("staff_existing_elsewhere"):
            warnings.append(
                f"Có {inventory['staff_existing_elsewhere']} nhân sự đã có hồ sơ năm hiện hành ở trường khác; engine sẽ không clone về trường đích."
            )

        impact_state_fingerprint, impact_state_summary = _impact_state_fingerprint(
            con,
            plan=plan,
            selected_year_id=int(selected_year_id),
            previous_year_id=previous_year_id,
            target_school_id=target_id,
            source_ids=source_ids,
        )

        year_code_by_id = {int(x["id"]): str(x.get("code") or x.get("name") or x["id"]) for x in years}
        move_year_codes = [year_code_by_id.get(int(x), str(x)) for x in inventory.get("move_year_ids") or []]
        past_year_codes = [year_code_by_id.get(int(x), str(x)) for x in inventory.get("past_year_ids") or []]

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

        simulation_result = None
        simulation_error = ""
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
                    selected_year_id=int(selected_year_id),
                    previous_year_id=previous_year_id,
                    target_school_id=target_id,
                    source_ids=source_ids,
                    actor_user_id=None,
                    record_audit=False,
                )
                mem.rollback()
            except Exception as exc:
                simulation_error = str(exc)
                blockers.append("Mô phỏng kỹ thuật trên bản sao bộ nhớ thất bại: " + simulation_error)
                if mem is not None:
                    try:
                        mem.rollback()
                    except Exception:
                        pass
            finally:
                if mem is not None:
                    mem.close()

    database_fingerprint_after = _database_state_fingerprint()
    if database_fingerprint_before != database_fingerprint_after:
        blockers.append(
            "Database đã thay đổi trong lúc lập bản xem trước. Hãy tải lại trang để lấy một bản xem trước ổn định."
        )

    direct_move_total = sum(int(x.get("current_year_rows") or 0) for x in direct_rows)
    historical_preserve_total = int(inventory.get("historical_total") or 0) + sum(
        int(x.get("preserve_rows") or 0) for x in no_year_rows
    )
    no_year_move_total = sum(int(x.get("move_rows") or 0) for x in no_year_rows)

    preview = {
        "plan": plan,
        "keep_only": False,
        "school_year": selected_year,
        "previous_year": previous_year,
        "move_year_codes": move_year_codes,
        "past_year_codes": past_year_codes,
        "target_school": checked_target or target,
        "source_schools": checked_sources or sources,
        "inventory": inventory,
        "direct_rows": direct_rows,
        "no_year_rows": no_year_rows,
        "summary": {
            "direct_move_rows": direct_move_total,
            "no_year_move_rows": no_year_move_total,
            "historical_preserve_rows": historical_preserve_total,
            "users_move_target": int(inventory.get("users_move_target") or 0),
            "source_school_logins_disable": int(inventory.get("source_school_logins_disable") or 0),
            "staff_rollover_candidates": int(inventory.get("staff_rollover_candidates") or 0),
            "sources_deactivate": len(source_ids),
        },
        "warnings": warnings,
        "blockers": blockers,
        "completed_operation": completed,
        "simulation_result": simulation_result,
        "simulation_error": simulation_error,
        "simulation_ok": not blockers and simulation_result is not None,
        "safe_for_future_execution": not blockers and simulation_result is not None,
        "execution_enabled": not blockers and simulation_result is not None,
        "database_fingerprint": database_fingerprint_after,
        "impact_state_fingerprint": impact_state_fingerprint,
        "impact_state_summary": impact_state_summary,
        "v41_state_check_ok": bool(impact_state_fingerprint) and not blockers and simulation_result is not None,
        "source_audit": source_audit,
        "v43_source_check_ok": bool(source_audit and source_audit.get("pass")),
        "rules": [
            "Giữ nguyên school_id của trường đích.",
            "Không xóa trường nguồn; khi thực hiện thật chỉ chuyển trường nguồn sang trạng thái ngừng hoạt động/đã sáp nhập.",
            "Dữ liệu năm hiệu lực và các năm tương lai chuyển về trường đích theo chính sách engine.",
            "Dữ liệu các năm trước năm hiệu lực giữ nguyên school_id trường cũ để bảo toàn lịch sử.",
            "Tài khoản trường nguồn sẽ khóa; tài khoản CBQL/GV/khác chỉ chuyển khi chính sách cho phép.",
            "V4.1 khóa trạng thái logic của đúng tập dữ liệu có thể tác động; backend tính lại ngay sau BEGIN IMMEDIATE và bắt xem trước lại nếu fingerprint đổi.",
            "V4.3 bắt buộc đối chiếu dữ liệu nguồn theo địa bàn + tên trường + mã trường DB + danh sách đội ngũ đang hoạt động/chuyển đến trước khi mở thực hiện.",
            "Nếu chưa có nguồn đối chiếu cho một trường/cấp học, hoặc số người/nhân thân/vị trí năm nguồn không khớp, V4.3 khóa thực hiện.",
            "Bản XEM TRƯỚC luôn chỉ mô phỏng trong RAM. Chỉ POST V4.3 có xác nhận đúng mới được phép ghi database.",
        ],
    }
    preview["fingerprint"] = _fingerprint(preview)
    return preview
