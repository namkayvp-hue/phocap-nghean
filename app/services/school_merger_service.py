from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from app.database import DATABASE_PATH


PROJECT_DIR = Path(__file__).resolve().parent.parent.parent
EXPORT_DIR = PROJECT_DIR / "exports"
CONFIRM_PHRASE = "SAP NHAP TRUONG"

SPECIAL_YEAR_TABLES = {
    "classes",
    "student_enrollments",
    "staff_year_records",
}

AUDIT_NO_YEAR_TABLES = {
    "survey_execution_workflow_logs",
    "survey_team_registration_logs",
}

MERGER_AUDIT_TABLES = {
    "school_merger_operations",
}

# V9.2.2: mọi thao tác sáp nhập phải khớp chính xác một phương án/văn bản
# đã được phê duyệt trước. Không còn chế độ chọn nguồn/đích tự do.
MERGER_PLAN_FILE = PROJECT_DIR / "data" / "school_merger_approved_plans.json"
PLAN_STATUS_DRAFT = "DRAFT"
PLAN_STATUS_APPROVED = "APPROVED"
PLAN_STATUS_COMPLETED = "COMPLETED"
PLAN_STATUS_CANCELLED = "CANCELLED"

# V13 - Toàn tỉnh: chỉ thực hiện phương án đã có trong SỔ ĐĂNG KÝ VĂN BẢN CHÍNH THỨC.
# Không cho ghép nguồn/đích tự do và không cho tạo/sửa/phê duyệt thủ công trên UI.
SINGLE_DOCUMENT_LOCK = False
OFFICIAL_REGISTRY_LOCK = True
SINGLE_DOCUMENT_CODE = "QĐ 3805"
SINGLE_DOCUMENT_PLAN_IDS = {
    "QD3805-NGHI-LOC-MN-QUAN-HANH",
    "QD3805-NGHI-LOC-MN-NGHI-DIEN",
    "QD3805-NGHI-LOC-TH-NGHI-DIEN",
    "QD3805-NGHI-LOC-TH-NGHI-TRUNG",
    "QD3805-NGHI-LOC-THCS-NGHI-DIEN",
    "QD3805-NGHI-LOC-THCS-NGHI-TRUNG",
}
PLAN_APPROVE_PHRASE = "PHE DUYET PHUONG AN"
PLAN_CANCEL_PHRASE = "HUY PHUONG AN"
PLAN_BACKUP_DIR = PROJECT_DIR / "backups"

# === V13_5_2_CURRENT_FUTURE_SCOPE ===
# Quy tắc thời gian:
# - PAST: giữ nguyên ở trường nguồn.
# - CURRENT + FUTURE: đi theo trường đích.
# Không bao giờ so sánh school_year_id để suy ra thứ tự năm học.


def _year_start_value(item: dict[str, Any]) -> int | None:
    text = str(item.get("code") or item.get("name") or "")
    match = re.search(r"(\d{4})\D+(\d{4})", text)
    return int(match.group(1)) if match else None


def _year_scope_ids(
    con: sqlite3.Connection,
    selected_year_id: int,
) -> tuple[list[int], list[int]]:
    years = _school_year_rows(con)
    selected = next(
        (x for x in years if int(x["id"]) == int(selected_year_id)),
        None,
    )
    if selected is None:
        raise SchoolMergerError("Không tìm thấy năm học sáp nhập.")

    selected_start = _year_start_value(selected)
    if selected_start is None:
        raise SchoolMergerError(
            "Không xác định được thứ tự năm học sáp nhập từ code/name."
        )

    move_ids: list[int] = []
    past_ids: list[int] = []
    unresolved: list[str] = []

    for item in years:
        start = _year_start_value(item)
        if start is None:
            unresolved.append(
                f"id={item.get('id')} / "
                f"{item.get('code') or item.get('name') or ''}"
            )
            continue
        if start >= selected_start:
            move_ids.append(int(item["id"]))
        else:
            past_ids.append(int(item["id"]))

    if unresolved:
        raise SchoolMergerError(
            "Có năm học không phân loại được PAST/CURRENT/FUTURE: "
            + " | ".join(unresolved)
        )

    if int(selected_year_id) not in move_ids:
        raise SchoolMergerError(
            "Năm học sáp nhập không nằm trong phạm vi CURRENT/FUTURE."
        )

    return sorted(set(move_ids)), sorted(set(past_ids))


class SchoolMergerError(RuntimeError):
    pass


def _quote_ident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def _markers(n: int) -> str:
    return ",".join("?" for _ in range(n))


def _connect(*, read_only: bool) -> sqlite3.Connection:
    if read_only:
        uri = DATABASE_PATH.resolve().as_uri() + "?mode=ro"
        con = sqlite3.connect(uri, uri=True, timeout=30)
    else:
        con = sqlite3.connect(str(DATABASE_PATH), timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    if read_only:
        con.execute("PRAGMA query_only=ON")
    return con


def _table_exists(con: sqlite3.Connection, table: str) -> bool:
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (table,),
    ).fetchone() is not None


def _all_tables(con: sqlite3.Connection) -> list[str]:
    return [
        str(r[0])
        for r in con.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
    ]


def _columns(con: sqlite3.Connection, table: str) -> list[dict[str, Any]]:
    return [
        {
            "cid": int(r[0]),
            "name": str(r[1]),
            "type": str(r[2] or ""),
            "notnull": bool(r[3]),
            "default": r[4],
            "pk": int(r[5] or 0),
        }
        for r in con.execute(f"PRAGMA table_info({_quote_ident(table)})").fetchall()
    ]


def _column_names(con: sqlite3.Connection, table: str) -> set[str]:
    return {x["name"] for x in _columns(con, table)}


def _simple_pk(con: sqlite3.Connection, table: str) -> str | None:
    items = sorted(
        ((x["pk"], x["name"]) for x in _columns(con, table) if x["pk"]),
        key=lambda x: x[0],
    )
    return items[0][1] if len(items) == 1 else None


def _foreign_keys(con: sqlite3.Connection, table: str) -> list[dict[str, str]]:
    return [
        {
            "parent_table": str(r[2]),
            "from_col": str(r[3]),
            "to_col": str(r[4] or "id"),
        }
        for r in con.execute(
            f"PRAGMA foreign_key_list({_quote_ident(table)})"
        ).fetchall()
    ]


def _normalize(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def _school_year_rows(con: sqlite3.Connection) -> list[dict[str, Any]]:
    if not _table_exists(con, "school_years"):
        return []
    cs = _column_names(con, "school_years")
    code_col = "code" if "code" in cs else None
    name_col = "name" if "name" in cs else None
    rows = con.execute("SELECT * FROM school_years ORDER BY id DESC").fetchall()
    return [
        {
            "id": int(r["id"]),
            "code": str(r[code_col] or "") if code_col else "",
            "name": str(r[name_col] or "") if name_col else "",
            "is_active": bool(r["is_active"]) if "is_active" in cs else True,
        }
        for r in rows
    ]


def list_school_years() -> list[dict[str, Any]]:
    with _connect(read_only=True) as con:
        return _school_year_rows(con)


def _previous_year_id(con: sqlite3.Connection, selected_year_id: int) -> int | None:
    years = _school_year_rows(con)
    selected = next((x for x in years if x["id"] == selected_year_id), None)
    if selected is None:
        return None

    code = str(selected.get("code") or "")
    match = re.search(r"(\d{4})\D+(\d{4})", code)
    if match:
        start = int(match.group(1))
        wanted = f"{start - 1}-{start}"
        for item in years:
            normalized = str(item.get("code") or "").replace("–", "-").replace("—", "-")
            if normalized == wanted:
                return int(item["id"])

    smaller = sorted((int(x["id"]) for x in years if int(x["id"]) < selected_year_id), reverse=True)
    return smaller[0] if smaller else None


def list_communes() -> list[dict[str, Any]]:
    with _connect(read_only=True) as con:
        if not _table_exists(con, "communes"):
            return []
        rows = con.execute(
            "SELECT id,code,name,is_active FROM communes ORDER BY name COLLATE NOCASE"
        ).fetchall()
        return [dict(r) for r in rows]


def _school_levels(con: sqlite3.Connection, school_id: int, year_id: int) -> set[str]:
    if not _table_exists(con, "school_network_year_data"):
        return set()
    cs = _column_names(con, "school_network_year_data")
    if not {"school_id", "school_year_id", "level_code"} <= cs:
        return set()

    rows = con.execute(
        "SELECT DISTINCT level_code FROM school_network_year_data "
        "WHERE school_id=? AND school_year_id=? AND level_code IS NOT NULL",
        (school_id, year_id),
    ).fetchall()
    levels = {str(r[0]).strip().upper() for r in rows if str(r[0] or "").strip()}
    if levels:
        return levels

    row = con.execute(
        "SELECT MAX(school_year_id) FROM school_network_year_data "
        "WHERE school_id=? AND school_year_id<=?",
        (school_id, year_id),
    ).fetchone()
    fallback_year = int(row[0]) if row and row[0] is not None else None
    if fallback_year is None:
        return set()
    rows = con.execute(
        "SELECT DISTINCT level_code FROM school_network_year_data "
        "WHERE school_id=? AND school_year_id=? AND level_code IS NOT NULL",
        (school_id, fallback_year),
    ).fetchall()
    return {str(r[0]).strip().upper() for r in rows if str(r[0] or "").strip()}


def _load_merger_plan_payload() -> dict[str, Any]:
    """Đọc file phương án sáp nhập đã phê duyệt.

    File này là cổng nghiệp vụ bắt buộc. Nếu file thiếu/hỏng, chức năng xem trước
    có thể hiển thị nhưng tuyệt đối không được phép thực hiện thật.
    """
    if not MERGER_PLAN_FILE.exists():
        return {"version": 1, "plans": [], "load_error": f"Không tìm thấy {MERGER_PLAN_FILE}"}
    try:
        payload = json.loads(MERGER_PLAN_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"version": 1, "plans": [], "load_error": f"Không đọc được file phương án: {exc}"}
    if not isinstance(payload, dict):
        return {"version": 1, "plans": [], "load_error": "File phương án phải là JSON object."}
    plans = payload.get("plans")
    if not isinstance(plans, list):
        return {"version": 1, "plans": [], "load_error": "File phương án thiếu mảng plans."}
    payload.setdefault("version", 1)
    payload.setdefault("load_error", "")
    return payload


def _normalize_plan(plan: dict[str, Any]) -> dict[str, Any]:
    item = dict(plan or {})
    item["id"] = str(item.get("id") or "").strip()
    item["document_code"] = str(item.get("document_code") or "").strip()
    item["document_title"] = str(item.get("document_title") or "").strip()
    item["status"] = str(item.get("status") or "").strip().upper()
    try:
        item["school_year_id"] = int(item.get("school_year_id"))
    except (TypeError, ValueError):
        item["school_year_id"] = None
    try:
        item["commune_id"] = int(item.get("commune_id")) if item.get("commune_id") is not None else None
    except (TypeError, ValueError):
        item["commune_id"] = None
    try:
        item["target_school_id"] = int(item.get("target_school_id"))
    except (TypeError, ValueError):
        item["target_school_id"] = None
    source_ids: list[int] = []
    for value in item.get("source_school_ids") or []:
        try:
            sid = int(value)
        except (TypeError, ValueError):
            continue
        if sid not in source_ids:
            source_ids.append(sid)
    item["source_school_ids"] = sorted(source_ids)
    return item


def _all_merger_plans() -> tuple[list[dict[str, Any]], str]:
    payload = _load_merger_plan_payload()
    return [_normalize_plan(x) for x in payload.get("plans") or [] if isinstance(x, dict)], str(payload.get("load_error") or "")


def _operation_matches_plan(
    con: sqlite3.Connection,
    plan: dict[str, Any],
) -> bool:
    """Một operation đã commit với đúng year/target/source => plan đã hoàn thành."""
    if not _table_exists(con, "school_merger_operations"):
        return False
    year_id = plan.get("school_year_id")
    target_id = plan.get("target_school_id")
    sources = sorted(set(int(x) for x in plan.get("source_school_ids") or []))
    if year_id is None or target_id is None or not sources:
        return False

    rows = con.execute(
        "SELECT source_school_ids_json FROM school_merger_operations "
        "WHERE school_year_id=? AND target_school_id=?",
        (int(year_id), int(target_id)),
    ).fetchall()
    for row in rows:
        try:
            actual = sorted(set(int(x) for x in json.loads(row[0] or "[]")))
        except Exception:
            continue
        if actual == sources:
            return True
    return False


def _effective_plan_status(
    con: sqlite3.Connection,
    plan: dict[str, Any],
) -> str:
    raw = str(plan.get("status") or "").strip().upper()
    if raw == PLAN_STATUS_CANCELLED:
        return PLAN_STATUS_CANCELLED
    if raw == PLAN_STATUS_COMPLETED or _operation_matches_plan(con, plan):
        return PLAN_STATUS_COMPLETED
    return raw


def _find_exact_merger_plan(
    *,
    selected_year_id: int,
    target_school_id: int,
    source_ids: list[int],
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], str]:
    plans, load_error = _all_merger_plans()
    wanted_sources = sorted(set(int(x) for x in source_ids))
    matches = [
        p for p in plans
        if p.get("school_year_id") == int(selected_year_id)
        and p.get("target_school_id") == int(target_school_id)
        and p.get("source_school_ids") == wanted_sources
    ]
    return (matches[0] if len(matches) == 1 else None), matches, load_error


def _validate_plan_gate(
    *,
    selected_year_id: int,
    target_school_id: int,
    source_ids: list[int],
) -> tuple[dict[str, Any] | None, list[str], list[str]]:
    blockers: list[str] = []
    warnings: list[str] = []
    plan, matches, load_error = _find_exact_merger_plan(
        selected_year_id=selected_year_id,
        target_school_id=target_school_id,
        source_ids=source_ids,
    )
    if load_error:
        blockers.append(
            "Không thể kiểm tra phương án sáp nhập đã phê duyệt: " + load_error
        )
        return None, blockers, warnings
    if len(matches) > 1:
        blockers.append(
            "Có nhiều phương án trùng cùng nguồn/đích/năm học trong file cấu hình; "
            "dừng an toàn."
        )
        return None, blockers, warnings
    if plan is None:
        blockers.append(
            "Nhóm trường nguồn → trường đích KHÔNG nằm trong QĐ 3805 đã khóa trong hệ thống. "
            "Hệ thống không cho phép ghép trường tự do hoặc dùng văn bản khác."
        )
        return None, blockers, warnings

    if SINGLE_DOCUMENT_LOCK:
        plan_id = str(plan.get("id") or "")
        document_code = str(plan.get("document_code") or "").strip()
        if plan_id not in SINGLE_DOCUMENT_PLAN_IDS or document_code != SINGLE_DOCUMENT_CODE:
            blockers.append(
                "Hệ thống hiện chỉ cho phép các nhóm sáp nhập thuộc đúng QĐ 3805 đã chốt. "
                "Phương án/văn bản khác bị khóa."
            )
            return None, blockers, warnings

    with _connect(read_only=True) as plan_con:
        effective_status = _effective_plan_status(plan_con, plan)
    plan = dict(plan)
    plan["effective_status"] = effective_status

    document_code = plan.get("document_code") or plan.get("id") or "phương án"
    if effective_status == PLAN_STATUS_COMPLETED:
        blockers.append(
            f"Phương án {document_code} đã HOÀN THÀNH; không được thực hiện lại "
            "hoặc dùng trường đích của phương án này để ghép tiếp ngoài văn bản mới."
        )
    elif effective_status != PLAN_STATUS_APPROVED:
        blockers.append(
            f"Phương án {document_code} chưa ở trạng thái ĐÃ DUYỆT – CHỜ THỰC HIỆN "
            f"(hiện: {effective_status or 'CHƯA XÁC ĐỊNH'})."
        )
    return plan, blockers, warnings


def _plan_data_summary(
    con: sqlite3.Connection,
    plan: dict[str, Any],
) -> dict[str, int]:
    """Thông tin dữ liệu để kiểm tra/hiển thị; không dùng để chọn partial merge."""
    year_id = int(plan.get("school_year_id") or 0)
    target_id = int(plan.get("target_school_id") or 0)
    source_ids = [int(x) for x in plan.get("source_school_ids") or []]
    previous_year_id = _previous_year_id(con, year_id)

    inv = _preview_inventory(
        con,
        selected_year_id=year_id,
        previous_year_id=previous_year_id,
        target_school_id=target_id,
        source_ids=source_ids,
    )

    direct = {
        str(r.get("table")): int(r.get("current_year_rows") or 0)
        for r in inv.get("direct_rows") or []
    }
    accounts = int(inv.get("users_move_target") or 0) + int(
        inv.get("source_school_logins_disable") or 0
    )
    staff = int(direct.get("staff_year_records", 0)) + int(
        inv.get("staff_rollover_candidates") or 0
    )
    classes = int(direct.get("classes", 0))
    students = int(direct.get("student_enrollments", 0))

    survey = 0
    other = 0
    for table, n in direct.items():
        if table in {"staff_year_records", "classes", "student_enrollments"}:
            continue
        if table.startswith("survey_"):
            survey += int(n)
        else:
            other += int(n)

    for r in inv.get("no_year_rows") or []:
        n = int(r.get("move_rows") or 0)
        table = str(r.get("table") or "")
        if table.startswith("survey_"):
            survey += n
        else:
            other += n

    return {
        "accounts": accounts,
        "staff": staff,
        "classes": classes,
        "students": students,
        "survey": survey,
        "other": other,
        "historical": int(inv.get("historical_total") or 0),
        "total_current": accounts + staff + classes + students + survey + other,
    }


def list_merger_plans(
    *,
    school_year_id: int | None = None,
    commune_id: int | None = None,
    level_code: str | None = None,
    display_mode: str = "all",
) -> list[dict[str, Any]]:
    plans, load_error = _all_merger_plans()
    if load_error:
        return []

    wanted_level = str(level_code or "").strip().upper()
    display_mode = str(display_mode or "all").strip().lower()
    if display_mode not in {"all", "approved", "completed"}:
        display_mode = "all"

    result: list[dict[str, Any]] = []
    with _connect(read_only=True) as con:
        for raw in plans:
            if SINGLE_DOCUMENT_LOCK and str(raw.get("id") or "") not in SINGLE_DOCUMENT_PLAN_IDS:
                continue
            if school_year_id is not None and raw.get("school_year_id") != int(school_year_id):
                continue

            target_id = raw.get("target_school_id")
            if target_id is None:
                continue
            target_row = _school_row(con, int(target_id))
            if target_row is None:
                continue

            plan_commune_id = raw.get("commune_id")
            actual_commune_id = int(target_row["commune_id"])
            if commune_id is not None and actual_commune_id != int(commune_id):
                continue
            if plan_commune_id is not None and int(plan_commune_id) != actual_commune_id:
                # Cấu hình sai xã: không đưa ra UI để tránh thao tác nhầm.
                continue

            plan_year_id = int(raw.get("school_year_id") or school_year_id or 0)
            target = dict(target_row)
            target["levels"] = sorted(
                _school_levels(con, int(target_id), plan_year_id)
            )

            plan_level = str(raw.get("level_code") or "").strip().upper()
            if wanted_level:
                if plan_level and plan_level != wanted_level:
                    continue
                if not plan_level and wanted_level not in set(target.get("levels") or []):
                    continue

            sources: list[dict[str, Any]] = []
            missing_source = False
            for sid in raw.get("source_school_ids") or []:
                row = _school_row(con, int(sid))
                if row is None:
                    missing_source = True
                    break
                item = dict(row)
                item["levels"] = sorted(
                    _school_levels(con, int(sid), plan_year_id)
                )
                sources.append(item)
            if missing_source or len(sources) != len(raw.get("source_school_ids") or []):
                continue

            item = dict(raw)
            effective_status = _effective_plan_status(con, item)

            # Màn hình THỰC HIỆN chỉ nhận phương án đã duyệt hoặc đã hoàn thành.
            # DRAFT/CANCELLED chỉ xuất hiện ở màn hình Quản lý phương án V9.4.
            if effective_status not in {PLAN_STATUS_APPROVED, PLAN_STATUS_COMPLETED}:
                continue
            if display_mode == "approved" and effective_status != PLAN_STATUS_APPROVED:
                continue
            if display_mode == "completed" and effective_status != PLAN_STATUS_COMPLETED:
                continue

            item["effective_status"] = effective_status
            item["target_school"] = target
            item["source_schools"] = sources
            item["status_label"] = {
                PLAN_STATUS_APPROVED: "ĐÃ DUYỆT – CHỜ THỰC HIỆN",
                PLAN_STATUS_COMPLETED: "ĐÃ HOÀN THÀNH",
                PLAN_STATUS_CANCELLED: "ĐÃ HỦY",
            }.get(
                effective_status,
                effective_status or "CHƯA XÁC ĐỊNH",
            )
            item["data_summary"] = _plan_data_summary(con, item)
            result.append(item)

    result.sort(
        key=lambda p: (
            str(p.get("level_code") or ""),
            str((p.get("target_school") or {}).get("name") or ""),
            str(p.get("id") or ""),
        )
    )
    return result



# ---------------------------------------------------------------------------
# V9.4 - QUẢN LÝ / NHẬP PHƯƠNG ÁN SÁP NHẬP THEO VĂN BẢN
# ---------------------------------------------------------------------------

def _actor_metadata(actor: dict[str, Any] | None) -> dict[str, Any]:
    actor = dict(actor or {})
    return {
        "user_id": actor.get("id") or actor.get("user_id"),
        "username": str(actor.get("username") or "").strip(),
        "full_name": str(actor.get("full_name") or actor.get("name") or "").strip(),
    }


def _plan_status_label(status: str) -> str:
    return {
        PLAN_STATUS_DRAFT: "NHÁP",
        PLAN_STATUS_APPROVED: "ĐÃ DUYỆT – CHỜ THỰC HIỆN",
        PLAN_STATUS_COMPLETED: "ĐÃ HOÀN THÀNH",
        PLAN_STATUS_CANCELLED: "ĐÃ HỦY",
    }.get(str(status or "").upper(), str(status or "CHƯA XÁC ĐỊNH"))


def _plan_payload_for_write() -> dict[str, Any]:
    if not MERGER_PLAN_FILE.exists():
        return {
            "version": 3,
            "revision": 0,
            "policy": (
                "Phương án mới phải lưu NHÁP, kiểm tra và PHÊ DUYỆT trước khi "
                "được đưa sang màn hình thực hiện sáp nhập."
            ),
            "plans": [],
        }
    payload = _load_merger_plan_payload()
    load_error = str(payload.get("load_error") or "")
    if load_error:
        raise SchoolMergerError(load_error)
    if not isinstance(payload.get("plans"), list):
        raise SchoolMergerError("File phương án thiếu mảng plans.")
    payload = dict(payload)
    payload.pop("load_error", None)
    payload.setdefault("revision", 0)
    return payload


def _write_merger_plan_payload(payload: dict[str, Any]) -> Path | None:
    """Ghi JSON nguyên tử và backup file cũ trước mọi mutation."""
    MERGER_PLAN_FILE.parent.mkdir(parents=True, exist_ok=True)
    PLAN_BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    backup_path: Path | None = None
    if MERGER_PLAN_FILE.exists():
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        backup_path = PLAN_BACKUP_DIR / f"school_merger_approved_plans_before_{stamp}.json"
        shutil.copy2(MERGER_PLAN_FILE, backup_path)

    out = dict(payload)
    out["version"] = max(int(out.get("version") or 1), 3)
    out["revision"] = int(out.get("revision") or 0) + 1
    out["updated_at"] = datetime.now().isoformat(timespec="seconds")
    out.setdefault(
        "policy",
        "Chỉ phương án APPROVED mới được xem trước/thực hiện; nguồn/đích lấy đúng theo văn bản.",
    )

    raw = json.dumps(out, ensure_ascii=False, indent=2)
    # Tự parse lại trước khi thay file thật.
    json.loads(raw)

    tmp = MERGER_PLAN_FILE.with_name(MERGER_PLAN_FILE.name + ".tmp")
    tmp.write_text(raw, encoding="utf-8")
    os.replace(tmp, MERGER_PLAN_FILE)
    return backup_path


def _plan_by_id_from_payload(payload: dict[str, Any], plan_id: str) -> tuple[int, dict[str, Any]]:
    wanted = str(plan_id or "").strip()
    for idx, raw in enumerate(payload.get("plans") or []):
        if isinstance(raw, dict) and str(raw.get("id") or "").strip() == wanted:
            return idx, dict(raw)
    raise SchoolMergerError(f"Không tìm thấy phương án: {wanted}")


def get_merger_plan_record(plan_id: str) -> dict[str, Any] | None:
    plans, load_error = _all_merger_plans()
    if load_error:
        raise SchoolMergerError(load_error)
    raw = next((p for p in plans if p.get("id") == str(plan_id or "").strip()), None)
    if raw is None:
        return None
    with _connect(read_only=True) as con:
        return _enrich_plan_admin(con, raw)


def _enrich_plan_admin(con: sqlite3.Connection, raw: dict[str, Any]) -> dict[str, Any]:
    item = dict(raw)
    target_id = item.get("target_school_id")
    target = dict(_school_row(con, int(target_id))) if target_id is not None and _school_row(con, int(target_id)) else None
    if target is not None and item.get("school_year_id") is not None:
        target["levels"] = sorted(_school_levels(con, int(target_id), int(item["school_year_id"])))

    sources: list[dict[str, Any]] = []
    for sid in item.get("source_school_ids") or []:
        row = _school_row(con, int(sid))
        if row is None:
            continue
        src = dict(row)
        if item.get("school_year_id") is not None:
            src["levels"] = sorted(_school_levels(con, int(sid), int(item["school_year_id"])))
        sources.append(src)

    effective = _effective_plan_status(con, item)
    item["effective_status"] = effective
    item["status_label"] = _plan_status_label(effective)
    item["target_school"] = target
    item["source_schools"] = sources
    return item


def list_merger_plan_admin(
    *,
    school_year_id: int | None = None,
    commune_id: int | None = None,
    level_code: str | None = None,
    status: str | None = None,
) -> list[dict[str, Any]]:
    plans, load_error = _all_merger_plans()
    if load_error:
        raise SchoolMergerError(load_error)
    wanted_level = str(level_code or "").strip().upper()
    wanted_status = str(status or "").strip().upper()
    result: list[dict[str, Any]] = []
    with _connect(read_only=True) as con:
        for raw in plans:
            if SINGLE_DOCUMENT_LOCK and str(raw.get("id") or "") not in SINGLE_DOCUMENT_PLAN_IDS:
                continue
            if school_year_id is not None and raw.get("school_year_id") != int(school_year_id):
                continue
            if commune_id is not None and raw.get("commune_id") != int(commune_id):
                continue
            if wanted_level and str(raw.get("level_code") or "").upper() != wanted_level:
                continue
            item = _enrich_plan_admin(con, raw)
            if wanted_status and item.get("effective_status") != wanted_status:
                continue
            result.append(item)
    result.sort(
        key=lambda p: (
            int(p.get("school_year_id") or 0),
            int(p.get("commune_id") or 0),
            str(p.get("level_code") or ""),
            str(p.get("document_code") or ""),
            str(p.get("id") or ""),
        )
    )
    return result


def _validate_plan_definition(
    *,
    school_year_id: int,
    commune_id: int,
    level_code: str,
    source_school_ids: list[int],
    target_school_id: int,
    current_plan_id: str | None = None,
    for_approval: bool,
) -> tuple[list[str], list[str]]:
    blockers: list[str] = []
    warnings: list[str] = []
    level = str(level_code or "").strip().upper()
    sources = sorted(set(int(x) for x in source_school_ids))
    target_id = int(target_school_id)

    if level not in {"MN", "TH", "THCS", "THPT"}:
        blockers.append("Cấp học không hợp lệ.")
    if not sources:
        blockers.append("Phải có ít nhất một trường nguồn.")
    if target_id in sources:
        blockers.append("Trường đích không được đồng thời là trường nguồn.")

    with _connect(read_only=True) as con:
        years = {int(x["id"]) for x in _school_year_rows(con)}
        if int(school_year_id) not in years:
            blockers.append("Năm học không tồn tại trong hệ thống.")

        involved = sources + [target_id]
        seen_rows: dict[int, sqlite3.Row] = {}
        for sid in involved:
            row = _school_row(con, sid)
            if row is None:
                blockers.append(f"Không tìm thấy trường id={sid}.")
                continue
            seen_rows[sid] = row
            if int(row["commune_id"]) != int(commune_id):
                blockers.append(
                    f"{row['name']} không thuộc xã/phường đã chọn."
                )
            if not bool(row["is_active"]):
                blockers.append(
                    f"{row['name']} đang bị khóa; không thể đưa vào phương án mới chờ thực hiện."
                )
            levels = _school_levels(con, sid, int(school_year_id))
            if level and level not in levels:
                blockers.append(
                    f"{row['name']} không thuộc cấp {level} trong năm học đã chọn."
                )

        plans, load_error = _all_merger_plans()
        if load_error:
            blockers.append(load_error)
        else:
            for other in plans:
                if current_plan_id and other.get("id") == current_plan_id:
                    continue
                other_status = _effective_plan_status(con, other)
                if other_status == PLAN_STATUS_CANCELLED:
                    continue
                same_exact = (
                    other.get("school_year_id") == int(school_year_id)
                    and other.get("target_school_id") == target_id
                    and sorted(other.get("source_school_ids") or []) == sources
                )
                if same_exact:
                    blockers.append(
                        f"Đã tồn tại phương án trùng nguồn/đích: {other.get('document_code') or other.get('id')}."
                    )
                    continue

                # Chỉ khóa xung đột với plan đang chờ thực hiện. COMPLETED không khóa
                # một văn bản mới về sau; DRAFT khác chỉ cảnh báo cho người soạn.
                if other.get("school_year_id") != int(school_year_id):
                    continue
                overlap = sorted(
                    set(involved)
                    & set((other.get("source_school_ids") or []) + [other.get("target_school_id")])
                )
                if not overlap:
                    continue
                if other_status == PLAN_STATUS_APPROVED:
                    blockers.append(
                        "Có trường đang nằm trong một phương án ĐÃ DUYỆT khác cùng năm học: "
                        + (other.get("document_code") or other.get("id") or "")
                    )
                elif other_status == PLAN_STATUS_DRAFT:
                    warnings.append(
                        "Có trường trùng với một phương án NHÁP khác: "
                        + (other.get("document_code") or other.get("id") or "")
                    )

    return blockers, warnings


def _technical_check_plan_for_approval(plan: dict[str, Any]) -> dict[str, Any]:
    """Mô phỏng kỹ thuật giống preview nhưng bỏ cổng status=APPROVED."""
    year_id = int(plan["school_year_id"])
    target_id = int(plan["target_school_id"])
    source_ids = sorted(set(int(x) for x in plan.get("source_school_ids") or []))
    with _connect(read_only=True) as con:
        integrity = str(con.execute("PRAGMA integrity_check").fetchone()[0])
        previous_year_id = _previous_year_id(con, year_id)
        target, sources, blockers, warnings = _validate_selection(
            con,
            selected_year_id=year_id,
            target_school_id=target_id,
            source_ids=source_ids,
            require_active_sources=True,
        )
        if integrity.lower() != "ok":
            blockers.append(f"Database không đạt integrity_check: {integrity}")

        inventory = _preview_inventory(
            con,
            selected_year_id=year_id,
            previous_year_id=previous_year_id,
            target_school_id=target_id,
            source_ids=source_ids,
        ) if target and sources else {
            "direct_rows": [], "historical_total": 0,
            "source_school_logins_disable": 0, "users_move_target": 0,
            "staff_rollover_candidates": 0, "staff_existing_elsewhere": 0,
            "staff_previous_duplicates": 0, "staff_unclassified": 0,
            "no_year_rows": [], "no_year_blockers": [],
        }
        blockers.extend(inventory.get("no_year_blockers") or [])
        if inventory.get("staff_previous_duplicates"):
            blockers.append(
                f"Đội ngũ năm trước có {inventory['staff_previous_duplicates']} staff_member_id trùng trong nhóm gộp."
            )
        if inventory.get("staff_unclassified"):
            blockers.append(
                f"Có {inventory['staff_unclassified']} hồ sơ đội ngũ năm trước chưa phân loại được."
            )
        if inventory.get("staff_existing_elsewhere"):
            warnings.append(
                f"Có {inventory['staff_existing_elsewhere']} nhân sự đã có hồ sơ năm hiện hành ở trường khác; engine sẽ không clone về đích."
            )

        simulation_result = None
        if not blockers and target and sources:
            mem = None
            try:
                mem = sqlite3.connect(":memory:")
                mem.row_factory = sqlite3.Row
                con.backup(mem)
                mem.execute("PRAGMA foreign_keys=ON")
                mem.execute("BEGIN")
                simulation_result = _apply_merge(
                    mem,
                    selected_year_id=year_id,
                    previous_year_id=previous_year_id,
                    target_school_id=target_id,
                    source_ids=source_ids,
                    actor_user_id=None,
                    record_audit=False,
                )
                mem.rollback()
            except Exception as exc:
                blockers.append("Mô phỏng kỹ thuật thất bại: " + str(exc))
            finally:
                if mem is not None:
                    try:
                        mem.close()
                    except Exception:
                        pass

    return {
        "blockers": blockers,
        "warnings": warnings,
        "inventory": inventory,
        "simulation_result": simulation_result,
        "safe_to_approve": not blockers and simulation_result is not None,
    }


def _new_plan_id(
    *,
    school_year_id: int,
    commune_id: int,
    level_code: str,
    document_code: str,
) -> str:
    stamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
    digest = hashlib.sha1(
        f"{document_code}|{school_year_id}|{commune_id}|{level_code}|{stamp}".encode("utf-8")
    ).hexdigest()[:7].upper()
    return f"PA-{school_year_id}-{commune_id}-{str(level_code).upper()}-{stamp[-10:]}-{digest}"


def save_merger_plan_draft(
    *,
    school_year_id: int,
    commune_id: int,
    level_code: str,
    document_code: str,
    document_title: str,
    document_date: str,
    source_school_ids: list[int],
    target_school_id: int,
    note: str,
    actor: dict[str, Any] | None,
    plan_id: str | None = None,
) -> dict[str, Any]:
    if OFFICIAL_REGISTRY_LOCK:
        raise SchoolMergerError(
            "Sổ phương án sáp nhập toàn tỉnh chỉ được nạp từ văn bản chính thức "
            "bằng bộ nhập V13; không cho tạo, sửa, phê duyệt, hủy hoặc xóa thủ công."
        )
    document_code = str(document_code or "").strip()
    document_title = str(document_title or "").strip()
    document_date = str(document_date or "").strip()
    note = str(note or "").strip()
    level = str(level_code or "").strip().upper()
    if not document_code:
        raise SchoolMergerError("Phải nhập Số/Ký hiệu văn bản.")
    if not document_title:
        raise SchoolMergerError("Phải nhập tên/nội dung văn bản hoặc phương án.")

    blockers, warnings = _validate_plan_definition(
        school_year_id=int(school_year_id),
        commune_id=int(commune_id),
        level_code=level,
        source_school_ids=source_school_ids,
        target_school_id=int(target_school_id),
        current_plan_id=str(plan_id or "") or None,
        for_approval=False,
    )
    if blockers:
        raise SchoolMergerError("Không thể lưu nháp: " + " | ".join(blockers))

    payload = _plan_payload_for_write()
    actor_meta = _actor_metadata(actor)
    now = datetime.now().isoformat(timespec="seconds")

    if plan_id:
        idx, existing = _plan_by_id_from_payload(payload, plan_id)
        normalized = _normalize_plan(existing)
        with _connect(read_only=True) as con:
            effective = _effective_plan_status(con, normalized)
        if effective != PLAN_STATUS_DRAFT:
            raise SchoolMergerError("Chỉ phương án NHÁP mới được sửa.")
        created_at = existing.get("created_at") or now
        created_by = existing.get("created_by") or actor_meta
        final_id = str(existing.get("id"))
    else:
        idx = None
        created_at = now
        created_by = actor_meta
        final_id = _new_plan_id(
            school_year_id=int(school_year_id),
            commune_id=int(commune_id),
            level_code=level,
            document_code=document_code,
        )

    record = {
        "id": final_id,
        "document_code": document_code,
        "document_title": document_title,
        "document_date": document_date,
        "school_year_id": int(school_year_id),
        "commune_id": int(commune_id),
        "level_code": level,
        "source_school_ids": sorted(set(int(x) for x in source_school_ids)),
        "target_school_id": int(target_school_id),
        "status": PLAN_STATUS_DRAFT,
        "note": note,
        "created_at": created_at,
        "created_by": created_by,
        "updated_at": now,
        "updated_by": actor_meta,
        "draft_warnings": warnings,
    }

    if idx is None:
        payload.setdefault("plans", []).append(record)
    else:
        payload["plans"][idx] = record
    backup = _write_merger_plan_payload(payload)
    result = dict(record)
    result["plan_file_backup"] = str(backup or "")
    return result


def approve_merger_plan(
    *,
    plan_id: str,
    actor: dict[str, Any] | None,
) -> dict[str, Any]:
    if OFFICIAL_REGISTRY_LOCK:
        raise SchoolMergerError(
            "Sổ phương án sáp nhập toàn tỉnh chỉ được nạp từ văn bản chính thức "
            "bằng bộ nhập V13; không cho tạo, sửa, phê duyệt, hủy hoặc xóa thủ công."
        )
    payload = _plan_payload_for_write()
    idx, existing = _plan_by_id_from_payload(payload, plan_id)
    plan = _normalize_plan(existing)
    with _connect(read_only=True) as con:
        effective = _effective_plan_status(con, plan)
    if effective != PLAN_STATUS_DRAFT:
        raise SchoolMergerError("Chỉ phương án NHÁP mới được phê duyệt.")

    blockers, warnings = _validate_plan_definition(
        school_year_id=int(plan["school_year_id"]),
        commune_id=int(plan["commune_id"]),
        level_code=str(plan.get("level_code") or ""),
        source_school_ids=list(plan.get("source_school_ids") or []),
        target_school_id=int(plan["target_school_id"]),
        current_plan_id=str(plan["id"]),
        for_approval=True,
    )
    technical = _technical_check_plan_for_approval(plan)
    blockers.extend(technical.get("blockers") or [])
    warnings.extend(technical.get("warnings") or [])
    if blockers:
        raise SchoolMergerError(
            "Phương án chưa đủ điều kiện phê duyệt: " + " | ".join(blockers)
        )

    actor_meta = _actor_metadata(actor)
    now = datetime.now().isoformat(timespec="seconds")
    updated = dict(existing)
    updated["status"] = PLAN_STATUS_APPROVED
    updated["approved_at"] = now
    updated["approved_by"] = actor_meta
    updated["updated_at"] = now
    updated["updated_by"] = actor_meta
    updated["approval_warnings"] = sorted(set(warnings))
    payload["plans"][idx] = updated
    backup = _write_merger_plan_payload(payload)
    result = dict(updated)
    result["technical_check"] = technical
    result["plan_file_backup"] = str(backup or "")
    return result


def cancel_merger_plan(
    *,
    plan_id: str,
    actor: dict[str, Any] | None,
) -> dict[str, Any]:
    if OFFICIAL_REGISTRY_LOCK:
        raise SchoolMergerError(
            "Sổ phương án sáp nhập toàn tỉnh chỉ được nạp từ văn bản chính thức "
            "bằng bộ nhập V13; không cho tạo, sửa, phê duyệt, hủy hoặc xóa thủ công."
        )
    payload = _plan_payload_for_write()
    idx, existing = _plan_by_id_from_payload(payload, plan_id)
    plan = _normalize_plan(existing)
    with _connect(read_only=True) as con:
        effective = _effective_plan_status(con, plan)
    if effective == PLAN_STATUS_COMPLETED:
        raise SchoolMergerError("Phương án đã hoàn thành, không thể hủy.")
    if effective == PLAN_STATUS_CANCELLED:
        raise SchoolMergerError("Phương án đã hủy trước đó.")
    if effective not in {PLAN_STATUS_DRAFT, PLAN_STATUS_APPROVED}:
        raise SchoolMergerError("Trạng thái phương án không cho phép hủy.")

    actor_meta = _actor_metadata(actor)
    now = datetime.now().isoformat(timespec="seconds")
    updated = dict(existing)
    updated["status"] = PLAN_STATUS_CANCELLED
    updated["cancelled_at"] = now
    updated["cancelled_by"] = actor_meta
    updated["updated_at"] = now
    updated["updated_by"] = actor_meta
    payload["plans"][idx] = updated
    backup = _write_merger_plan_payload(payload)
    result = dict(updated)
    result["plan_file_backup"] = str(backup or "")
    return result


def delete_merger_plan_draft(
    *,
    plan_id: str,
    actor: dict[str, Any] | None = None,
) -> Path | None:
    if OFFICIAL_REGISTRY_LOCK:
        raise SchoolMergerError(
            "Sổ phương án sáp nhập toàn tỉnh chỉ được nạp từ văn bản chính thức "
            "bằng bộ nhập V13; không cho tạo, sửa, phê duyệt, hủy hoặc xóa thủ công."
        )
    payload = _plan_payload_for_write()
    idx, existing = _plan_by_id_from_payload(payload, plan_id)
    plan = _normalize_plan(existing)
    with _connect(read_only=True) as con:
        effective = _effective_plan_status(con, plan)
    if effective != PLAN_STATUS_DRAFT:
        raise SchoolMergerError("Chỉ phương án NHÁP mới được xóa.")
    payload["plans"].pop(idx)
    return _write_merger_plan_payload(payload)


def list_schools(
    *,
    year_id: int,
    commune_id: int | None = None,
    level_code: str | None = None,
    include_inactive: bool = False,
) -> list[dict[str, Any]]:
    with _connect(read_only=True) as con:
        where: list[str] = []
        params: list[Any] = []
        if commune_id is not None:
            where.append("s.commune_id=?")
            params.append(int(commune_id))
        if not include_inactive:
            where.append("s.is_active=1")
        sql = (
            "SELECT s.id,s.code,s.name,s.commune_id,s.is_active,c.name AS commune_name "
            "FROM schools s JOIN communes c ON c.id=s.commune_id"
        )
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY c.name COLLATE NOCASE,s.name COLLATE NOCASE"
        result = []
        wanted_level = str(level_code or "").strip().upper()
        for row in con.execute(sql, params).fetchall():
            levels = _school_levels(con, int(row["id"]), int(year_id))
            if wanted_level and levels and wanted_level not in levels:
                continue
            if wanted_level and not levels:
                continue
            item = dict(row)
            item["levels"] = sorted(levels)
            item["level_text"] = ", ".join(sorted(levels)) or "Chưa xác định"
            result.append(item)
        return result


def _school_row(con: sqlite3.Connection, school_id: int) -> sqlite3.Row | None:
    return con.execute(
        "SELECT s.*,c.name AS commune_name FROM schools s "
        "JOIN communes c ON c.id=s.commune_id WHERE s.id=?",
        (school_id,),
    ).fetchone()


def _fetch_parent(
    con: sqlite3.Connection,
    table: str,
    column: str,
    value: Any,
) -> sqlite3.Row | None:
    if value is None or not _table_exists(con, table):
        return None
    try:
        return con.execute(
            f"SELECT * FROM {_quote_ident(table)} WHERE {_quote_ident(column)}=? LIMIT 1",
            (value,),
        ).fetchone()
    except sqlite3.Error:
        return None


def _resolve_indirect_year(
    con: sqlite3.Connection,
    table: str,
    row: sqlite3.Row,
    *,
    depth: int = 0,
    visited: set[tuple[str, Any]] | None = None,
) -> tuple[int | None, str]:
    if depth > 3:
        return None, "Quá độ sâu truy vết"

    visited = set(visited or set())
    row_id = row["id"] if "id" in row.keys() else id(row)
    key = (table, row_id)
    if key in visited:
        return None, "Vòng lặp FK"
    visited.add(key)

    keys = set(row.keys())
    if "school_year_id" in keys and row["school_year_id"] is not None:
        return int(row["school_year_id"]), f"{table}.school_year_id"

    if "survey_batch_id" in keys and row["survey_batch_id"] is not None and _table_exists(con, "survey_batches"):
        batch = _fetch_parent(con, "survey_batches", "id", row["survey_batch_id"])
        if batch is not None and "school_year_id" in batch.keys() and batch["school_year_id"] is not None:
            return int(batch["school_year_id"]), f"{table}.survey_batch_id->survey_batches.school_year_id"

    for fk in _foreign_keys(con, table):
        if fk["from_col"] not in keys:
            continue
        value = row[fk["from_col"]]
        if value is None:
            continue
        parent = _fetch_parent(con, fk["parent_table"], fk["to_col"], value)
        if parent is None:
            continue
        parent_keys = set(parent.keys())
        if "school_year_id" in parent_keys and parent["school_year_id"] is not None:
            return int(parent["school_year_id"]), (
                f"{table}.{fk['from_col']}->{fk['parent_table']}.school_year_id"
            )
        year_id, path = _resolve_indirect_year(
            con,
            fk["parent_table"],
            parent,
            depth=depth + 1,
            visited=visited,
        )
        if year_id is not None:
            return year_id, f"{table}.{fk['from_col']}->{path}"

    return None, "Không truy được school_year_id"


def _classify_staff(row: sqlite3.Row) -> str:
    keys = set(row.keys())
    text = " ".join(
        _normalize(row[c])
        for c in (
            "position_group",
            "position_title",
            "source_level",
            "teaching_level",
            "source_status_label",
        )
        if c in keys and row[c] not in (None, "")
    )
    if any(x in text for x in (
        "quan ly", "cbql", "hieu truong", "pho hieu truong",
        "principal", "manager", "management",
    )):
        return "QUAN_LY"
    if any(x in text for x in (
        "nhan vien", "ke toan", "van thu", "thu vien", "thiet bi",
        "y te", "bao ve", "phuc vu", "cap duong", "thu quy", "employee",
    )):
        return "NHAN_VIEN"
    if any(x in text for x in ("giao vien", "teacher", "teaching", "gv")):
        return "GIAO_VIEN"
    return "CHUA_XAC_DINH"


def _staff_inactive(row: sqlite3.Row) -> bool:
    keys = set(row.keys())
    if "is_active" in keys and row["is_active"] in (0, False, "0"):
        return True
    text = " ".join(
        _normalize(row[c])
        for c in ("status_code", "source_status_label", "notes")
        if c in keys and row[c] not in (None, "")
    )
    return any(x in text for x in (
        "nghi viec", "thoi viec", "nghi huu", "chuyen di", "da chuyen",
        "inactive", "resigned", "retired", "terminated",
    ))


def _clone_staff_record(
    con: sqlite3.Connection,
    source_row: sqlite3.Row,
    *,
    target_school_id: int,
    selected_year_id: int,
    target_commune_id: int,
) -> int:
    cols = [x["name"] for x in _columns(con, "staff_year_records")]
    insert_cols: list[str] = []
    values: list[Any] = []
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for col in cols:
        if col == "id":
            continue
        insert_cols.append(col)
        if col == "school_id":
            values.append(target_school_id)
        elif col == "school_year_id":
            values.append(selected_year_id)
        elif col == "commune_id":
            values.append(target_commune_id)
        elif col in {"created_at", "updated_at"}:
            values.append(now)
        else:
            values.append(source_row[col])
    sql = (
        "INSERT INTO staff_year_records ("
        + ",".join(_quote_ident(c) for c in insert_cols)
        + ") VALUES ("
        + _markers(len(insert_cols))
        + ")"
    )
    cur = con.execute(sql, values)
    return int(cur.lastrowid)


def _update_scope_sql(
    con: sqlite3.Connection,
    table: str,
    *,
    target_school_id: int,
    target_commune_id: int,
    where_sql: str,
    params: list[Any],
) -> sqlite3.Cursor:
    cs = _column_names(con, table)
    sets = ["school_id=?"]
    values: list[Any] = [target_school_id]
    if "commune_id" in cs:
        sets.append("commune_id=?")
        values.append(target_commune_id)
    return con.execute(
        f"UPDATE {_quote_ident(table)} SET " + ",".join(sets) + " WHERE " + where_sql,
        values + params,
    )


def _current_year_tables(con: sqlite3.Connection) -> list[str]:
    result = []
    for table in _all_tables(con):
        if table in MERGER_AUDIT_TABLES:
            continue
        cs = _column_names(con, table)
        if {"school_id", "school_year_id"} <= cs:
            result.append(table)
    return result


def _no_year_school_tables(con: sqlite3.Connection) -> list[str]:
    result = []
    for table in _all_tables(con):
        if table in MERGER_AUDIT_TABLES:
            continue
        cs = _column_names(con, table)
        if "school_id" in cs and "school_year_id" not in cs:
            result.append(table)
    return result


def _count_rows(
    con: sqlite3.Connection,
    table: str,
    *,
    source_ids: list[int],
    selected_year_id: int | None = None,
    selected: bool = True,
) -> int:
    cs = _column_names(con, table)
    if "school_id" not in cs:
        return 0
    params: list[Any] = list(source_ids)
    sql = (
        f"SELECT COUNT(*) FROM {_quote_ident(table)} "
        f"WHERE school_id IN ({_markers(len(source_ids))})"
    )
    if selected_year_id is not None and "school_year_id" in cs:
        sql += " AND school_year_id" + ("=?" if selected else "<>?")
        params.append(selected_year_id)
    return int(con.execute(sql, params).fetchone()[0] or 0)


def _count_rows_for_year_ids(
    con: sqlite3.Connection,
    table: str,
    *,
    source_ids: list[int],
    year_ids: list[int],
) -> int:
    cs = _column_names(con, table)
    if "school_id" not in cs or "school_year_id" not in cs:
        return 0
    if not source_ids or not year_ids:
        return 0
    params: list[Any] = [*source_ids, *year_ids]
    sql = (
        f"SELECT COUNT(*) FROM {_quote_ident(table)} "
        f"WHERE school_id IN ({_markers(len(source_ids))}) "
        f"AND school_year_id IN ({_markers(len(year_ids))})"
    )
    return int(con.execute(sql, params).fetchone()[0] or 0)



def _build_no_year_plan(
    con: sqlite3.Connection,
    *,
    source_ids: list[int],
    target_school_id: int,
    selected_year_id: int,
) -> tuple[list[dict[str, Any]], list[str]]:
    rows_out: list[dict[str, Any]] = []
    blockers: list[str] = []
    source_set = set(source_ids)
    move_year_ids, past_year_ids = _year_scope_ids(
        con,
        selected_year_id,
    )
    move_year_set = set(move_year_ids)

    for table in _no_year_school_tables(con):
        if table == "users":
            continue
        total = _count_rows(con, table, source_ids=source_ids)
        if total == 0:
            continue
        if table in AUDIT_NO_YEAR_TABLES or table.endswith("_logs"):
            rows_out.append({
                "table": table,
                "policy": "KEEP_AUDIT_LOG_AT_SOURCE",
                "move_rows": 0,
                "preserve_rows": total,
                "unresolved_rows": 0,
            })
            continue

        pk = _simple_pk(con, table)
        if pk is None:
            blockers.append(
                f"{table}: có dữ liệu nhưng không có khóa chính đơn để truy vết."
            )
            rows_out.append({
                "table": table,
                "policy": "REVIEW",
                "move_rows": 0,
                "preserve_rows": 0,
                "unresolved_rows": total,
            })
            continue

        table_rows = con.execute(
            f"SELECT * FROM {_quote_ident(table)} "
            f"WHERE school_id IN ({_markers(len(source_ids))}) "
            f"ORDER BY {_quote_ident(pk)}",
            source_ids,
        ).fetchall()

        move_rows = 0
        preserve_rows = 0
        unresolved_rows = 0

        for row in table_rows:
            sid = row["school_id"]
            if sid is None or int(sid) not in source_set:
                continue

            year_id, _ = _resolve_indirect_year(
                con,
                table,
                row,
            )
            if year_id is None:
                unresolved_rows += 1
            elif int(year_id) in move_year_set:
                move_rows += 1
            else:
                preserve_rows += 1

        if unresolved_rows:
            blockers.append(
                f"{table}: {unresolved_rows} dòng không truy được năm học gián tiếp."
            )

        rows_out.append({
            "table": table,
            "policy": (
                "MOVE_CURRENT_FUTURE_BY_INDIRECT_TRACE"
                if not unresolved_rows
                else "REVIEW"
            ),
            "move_rows": move_rows,
            "preserve_rows": preserve_rows,
            "unresolved_rows": unresolved_rows,
        })

    return rows_out, blockers



def _preview_inventory(
    con: sqlite3.Connection,
    *,
    selected_year_id: int,
    previous_year_id: int | None,
    target_school_id: int,
    source_ids: list[int],
) -> dict[str, Any]:
    move_year_ids, past_year_ids = _year_scope_ids(
        con,
        selected_year_id,
    )

    direct_rows: list[dict[str, Any]] = []
    historical_total = 0

    for table in _current_year_tables(con):
        current_future = _count_rows_for_year_ids(
            con,
            table,
            source_ids=source_ids,
            year_ids=move_year_ids,
        )
        historical = _count_rows_for_year_ids(
            con,
            table,
            source_ids=source_ids,
            year_ids=past_year_ids,
        )
        historical_total += historical

        if current_future or historical:
            if table == "classes":
                policy = "MOVE_CLASSES_CURRENT_FUTURE"
            elif table == "student_enrollments":
                policy = "MOVE_ENROLLMENTS_CURRENT_FUTURE"
            elif table == "staff_year_records":
                policy = "MOVE_CURRENT_FUTURE_AND_ROLLOVER_STAFF"
            else:
                policy = "MOVE_CURRENT_FUTURE_PRESERVE_PAST"

            direct_rows.append({
                "table": table,
                "policy": policy,
                # Giữ tên key cũ để template hiện tại tương thích.
                "current_year_rows": current_future,
                "historical_rows_preserve": historical,
            })

    users_total = 0
    school_logins = 0
    move_users = 0
    if _table_exists(con, "users"):
        users_total = int(con.execute(
            f"SELECT COUNT(*) FROM users "
            f"WHERE school_id IN ({_markers(len(source_ids))})",
            source_ids,
        ).fetchone()[0] or 0)

        school_logins = int(con.execute(
            f"SELECT COUNT(*) FROM users "
            f"WHERE school_id IN ({_markers(len(source_ids))}) "
            "AND username LIKE 'truong_%'",
            source_ids,
        ).fetchone()[0] or 0)

        move_users = users_total - school_logins

    staff_rollover_candidates = 0
    staff_rollover_skipped_existing_elsewhere = 0
    staff_previous_duplicates = 0
    staff_unclassified = 0

    if (
        previous_year_id is not None
        and _table_exists(con, "staff_year_records")
    ):
        origin_ids = sorted(
            set(source_ids + [target_school_id])
        )
        rows = con.execute(
            f"SELECT * FROM staff_year_records "
            f"WHERE school_year_id=? "
            f"AND school_id IN ({_markers(len(origin_ids))})",
            [previous_year_id] + origin_ids,
        ).fetchall()

        grouped: dict[int, list[sqlite3.Row]] = defaultdict(list)
        for row in rows:
            grouped[int(row["staff_member_id"])].append(row)

        for staff_id, items in grouped.items():
            if len(items) > 1:
                staff_previous_duplicates += 1
                continue

            row = items[0]
            if _classify_staff(row) == "CHUA_XAC_DINH":
                staff_unclassified += 1

            if _staff_inactive(row):
                continue

            existing = con.execute(
                "SELECT school_id FROM staff_year_records "
                "WHERE staff_member_id=? AND school_year_id=? LIMIT 1",
                (staff_id, selected_year_id),
            ).fetchone()

            if existing is None:
                staff_rollover_candidates += 1
            elif (
                int(existing["school_id"]) != target_school_id
                and int(existing["school_id"]) not in set(source_ids)
            ):
                staff_rollover_skipped_existing_elsewhere += 1

    no_year_rows, no_year_blockers = _build_no_year_plan(
        con,
        source_ids=source_ids,
        target_school_id=target_school_id,
        selected_year_id=selected_year_id,
    )

    return {
        "direct_rows": direct_rows,
        "historical_total": historical_total,
        "move_year_ids": move_year_ids,
        "past_year_ids": past_year_ids,
        "users_total": users_total,
        "source_school_logins_disable": school_logins,
        "users_move_target": move_users,
        "staff_rollover_candidates": staff_rollover_candidates,
        "staff_existing_elsewhere": (
            staff_rollover_skipped_existing_elsewhere
        ),
        "staff_previous_duplicates": staff_previous_duplicates,
        "staff_unclassified": staff_unclassified,
        "no_year_rows": no_year_rows,
        "no_year_blockers": no_year_blockers,
    }



def _validate_selection(
    con: sqlite3.Connection,
    *,
    selected_year_id: int,
    target_school_id: int,
    source_ids: list[int],
    require_active_sources: bool,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[str], list[str]]:
    blockers: list[str] = []
    warnings: list[str] = []

    years = _school_year_rows(con)
    year = next((x for x in years if int(x["id"]) == selected_year_id), None)
    if year is None:
        blockers.append("Năm học được chọn không tồn tại.")

    if not source_ids:
        blockers.append("Phải chọn ít nhất một trường nguồn.")
    source_ids = sorted(set(int(x) for x in source_ids))
    if target_school_id in source_ids:
        blockers.append("Trường đích không được đồng thời là trường nguồn.")

    target = _school_row(con, target_school_id)
    if target is None:
        blockers.append("Không tìm thấy trường đích.")
        target_dict: dict[str, Any] = {"id": target_school_id}
    else:
        target_dict = dict(target)
        target_dict["levels"] = sorted(_school_levels(con, target_school_id, selected_year_id))
        if not bool(target["is_active"]):
            blockers.append("Trường đích đang bị khóa; không cho phép sáp nhập vào trường đích đã khóa.")

    sources: list[dict[str, Any]] = []
    target_levels = set(target_dict.get("levels") or [])
    for sid in source_ids:
        row = _school_row(con, sid)
        if row is None:
            blockers.append(f"Không tìm thấy trường nguồn ID {sid}.")
            continue
        item = dict(row)
        item["levels"] = sorted(_school_levels(con, sid, selected_year_id))
        sources.append(item)
        if require_active_sources and not bool(row["is_active"]):
            blockers.append(
                f"Trường nguồn {row['name']} đang bị khóa. Chức năng thực hiện thật chỉ nhận trường nguồn đang hoạt động."
            )
        source_levels = set(item["levels"])
        if target_levels and source_levels and target_levels.isdisjoint(source_levels):
            blockers.append(
                f"Cấp học không khớp: {row['name']} ({', '.join(sorted(source_levels))}) -> "
                f"{target_dict.get('name', target_school_id)} ({', '.join(sorted(target_levels))})."
            )
        if int(row["commune_id"]) != int(target_dict.get("commune_id") or -1):
            warnings.append(
                f"{row['name']} khác xã/phường với trường đích; dữ liệu CURRENT/FUTURE và tài khoản chuyển sang đích sẽ dùng commune_id của trường đích."
            )

    if len(sources) != len(source_ids):
        blockers.append("Danh sách trường nguồn không đầy đủ.")

    # Một tài khoản Trường gốc đang hoạt động tại đích là cổng quan trọng.
    if target is not None and _table_exists(con, "users"):
        active_target_logins = int(con.execute(
            "SELECT COUNT(*) FROM users WHERE school_id=? AND is_active=1 AND username LIKE 'truong_%'",
            (target_school_id,),
        ).fetchone()[0] or 0)
        if active_target_logins != 1:
            blockers.append(
                f"Trường đích phải có đúng 1 tài khoản Trường gốc đang hoạt động; hiện có {active_target_logins}."
            )

    return target_dict, sources, blockers, warnings


def _apply_merge(
    con: sqlite3.Connection,
    *,
    selected_year_id: int,
    previous_year_id: int | None,
    target_school_id: int,
    source_ids: list[int],
    actor_user_id: int | None,
    backup_name: str = "",
    record_audit: bool = False,
) -> dict[str, Any]:
    target = _school_row(con, target_school_id)
    if target is None:
        raise SchoolMergerError("Không tìm thấy trường đích trong lúc thực hiện.")
    target_commune_id = int(target["commune_id"])
    source_ids = sorted(set(int(x) for x in source_ids))
    move_year_ids, past_year_ids = _year_scope_ids(
        con,
        selected_year_id,
    )
    move_year_set = set(move_year_ids)

    result: dict[str, Any] = {
        "move_year_ids": move_year_ids,
        "past_year_ids": past_year_ids,
        "direct_moves": [],
        "no_year_moves": [],
        "audit_logs_kept": [],
        "users_moved": 0,
        "source_school_logins_disabled": 0,
        "staff_rollover_created": 0,
        "staff_existing_elsewhere_skipped": 0,
        "sources_deactivated": 0,
    }

    # 1) Lớp CURRENT + FUTURE trước, để enrollment giữ class_id nhưng lớp đã thuộc target.
    if _table_exists(con, "classes"):
        for source_id in source_ids:
            cur = _update_scope_sql(
                con,
                "classes",
                target_school_id=target_school_id,
                target_commune_id=target_commune_id,
                where_sql=(
                    f"school_id=? AND school_year_id IN "
                    f"({_markers(len(move_year_ids))})"
                ),
                params=[source_id, *move_year_ids],
            )
            if cur.rowcount:
                result["direct_moves"].append({
                    "table": "classes", "source_school_id": source_id,
                    "target_school_id": target_school_id, "rows": max(cur.rowcount, 0),
                })

    # 2) Enrollment CURRENT + FUTURE.
    if _table_exists(con, "student_enrollments"):
        for source_id in source_ids:
            cur = _update_scope_sql(
                con,
                "student_enrollments",
                target_school_id=target_school_id,
                target_commune_id=target_commune_id,
                where_sql=(
                    f"school_id=? AND school_year_id IN "
                    f"({_markers(len(move_year_ids))})"
                ),
                params=[source_id, *move_year_ids],
            )
            if cur.rowcount:
                result["direct_moves"].append({
                    "table": "student_enrollments", "source_school_id": source_id,
                    "target_school_id": target_school_id, "rows": max(cur.rowcount, 0),
                })

    # 3) Đội ngũ CURRENT + FUTURE: chuyển trước.
    if _table_exists(con, "staff_year_records"):
        for source_id in source_ids:
            cur = _update_scope_sql(
                con,
                "staff_year_records",
                target_school_id=target_school_id,
                target_commune_id=target_commune_id,
                where_sql=(
                    f"school_id=? AND school_year_id IN "
                    f"({_markers(len(move_year_ids))})"
                ),
                params=[source_id, *move_year_ids],
            )
            if cur.rowcount:
                result["direct_moves"].append({
                    "table": "staff_year_records", "source_school_id": source_id,
                    "target_school_id": target_school_id, "rows": max(cur.rowcount, 0),
                })

        # Rollover phần còn thiếu từ năm trước của target + source.
        if previous_year_id is not None:
            origins = sorted(set(source_ids + [target_school_id]))
            previous_rows = con.execute(
                f"SELECT * FROM staff_year_records WHERE school_year_id=? "
                f"AND school_id IN ({_markers(len(origins))}) ORDER BY id",
                [previous_year_id] + origins,
            ).fetchall()
            grouped: dict[int, list[sqlite3.Row]] = defaultdict(list)
            for row in previous_rows:
                grouped[int(row["staff_member_id"])].append(row)
            duplicate_staff = [staff_id for staff_id, rows in grouped.items() if len(rows) > 1]
            if duplicate_staff:
                raise SchoolMergerError(
                    "Đội ngũ năm trước có trùng staff_member_id trong nhóm sáp nhập: "
                    + ", ".join(map(str, duplicate_staff[:20]))
                )

            for staff_id, rows in grouped.items():
                row = rows[0]
                if _classify_staff(row) == "CHUA_XAC_DINH":
                    raise SchoolMergerError(
                        f"Không phân loại được hồ sơ đội ngũ id={row['id']} / staff_member_id={staff_id}."
                    )
                if _staff_inactive(row):
                    continue
                existing = con.execute(
                    "SELECT id,school_id FROM staff_year_records "
                    "WHERE staff_member_id=? AND school_year_id=? LIMIT 1",
                    (staff_id, selected_year_id),
                ).fetchone()
                if existing is not None:
                    if int(existing["school_id"]) not in {target_school_id, *source_ids}:
                        result["staff_existing_elsewhere_skipped"] += 1
                    continue
                _clone_staff_record(
                    con,
                    row,
                    target_school_id=target_school_id,
                    selected_year_id=selected_year_id,
                    target_commune_id=target_commune_id,
                )
                result["staff_rollover_created"] += 1

    # 4) Mọi bảng school_id + school_year_id còn lại:
    # CURRENT + FUTURE chuyển về đích; PAST giữ nguyên.
    for table in _current_year_tables(con):
        if table in SPECIAL_YEAR_TABLES or table in MERGER_AUDIT_TABLES:
            continue
        for source_id in source_ids:
            cur = _update_scope_sql(
                con,
                table,
                target_school_id=target_school_id,
                target_commune_id=target_commune_id,
                where_sql=(
                    f"school_id=? AND school_year_id IN "
                    f"({_markers(len(move_year_ids))})"
                ),
                params=[source_id, *move_year_ids],
            )
            if cur.rowcount:
                result["direct_moves"].append({
                    "table": table,
                    "source_school_id": source_id,
                    "target_school_id": target_school_id,
                    "rows": max(cur.rowcount, 0),
                })

    # 5) Bảng có school_id nhưng không có school_year_id.
    for table in _no_year_school_tables(con):
        if table == "users" or table in MERGER_AUDIT_TABLES:
            continue
        total = _count_rows(con, table, source_ids=source_ids)
        if total == 0:
            continue
        if table in AUDIT_NO_YEAR_TABLES or table.endswith("_logs"):
            result["audit_logs_kept"].append({"table": table, "rows": total})
            continue
        pk = _simple_pk(con, table)
        if pk is None:
            raise SchoolMergerError(f"{table}: không có khóa chính đơn để xử lý an toàn.")
        rows = con.execute(
            f"SELECT * FROM {_quote_ident(table)} "
            f"WHERE school_id IN ({_markers(len(source_ids))}) ORDER BY {_quote_ident(pk)}",
            source_ids,
        ).fetchall()
        ids_by_source: dict[int, list[Any]] = defaultdict(list)
        unresolved: list[Any] = []
        for row in rows:
            year_id, _ = _resolve_indirect_year(con, table, row)
            if year_id is None:
                unresolved.append(row[pk])
            elif int(year_id) in move_year_set:
                ids_by_source[int(row["school_id"])].append(row[pk])
        if unresolved:
            raise SchoolMergerError(
                f"{table}: không truy được năm học cho {len(unresolved)} dòng; dừng an toàn."
            )
        for source_id, ids in ids_by_source.items():
            if not ids:
                continue
            cur = _update_scope_sql(
                con,
                table,
                target_school_id=target_school_id,
                target_commune_id=target_commune_id,
                where_sql=f"{_quote_ident(pk)} IN ({_markers(len(ids))})",
                params=list(ids),
            )
            result["no_year_moves"].append({
                "table": table,
                "source_school_id": source_id,
                "target_school_id": target_school_id,
                "rows": max(cur.rowcount, 0),
            })

    # 6) Tài khoản.
    if _table_exists(con, "users"):
        user_cs = _column_names(con, "users")
        for source_id in source_ids:
            cur = con.execute(
                "UPDATE users SET is_active=0 "
                "WHERE school_id=? AND username LIKE 'truong_%' AND is_active=1",
                (source_id,),
            )
            result["source_school_logins_disabled"] += max(cur.rowcount, 0)

            sets = ["school_id=?"]
            values: list[Any] = [target_school_id]
            if "commune_id" in user_cs:
                sets.append("commune_id=?")
                values.append(target_commune_id)
            cur = con.execute(
                "UPDATE users SET " + ",".join(sets)
                + " WHERE school_id=? AND username NOT LIKE 'truong_%'",
                values + [source_id],
            )
            result["users_moved"] += max(cur.rowcount, 0)

    # 7) Khóa trường nguồn.
    cur = con.execute(
        f"UPDATE schools SET is_active=0 WHERE id IN ({_markers(len(source_ids))})",
        source_ids,
    )
    result["sources_deactivated"] = max(cur.rowcount, 0)

    # 8) Kiểm tra sau thao tác.
    for table in _current_year_tables(con):
        if table in MERGER_AUDIT_TABLES:
            continue
        n = _count_rows_for_year_ids(
            con,
            table,
            source_ids=source_ids,
            year_ids=move_year_ids,
        )
        if n:
            raise SchoolMergerError(
                f"Sau sáp nhập vẫn còn {n} dòng CURRENT/FUTURE "
                f"ở trường nguồn trong bảng {table}."
            )

    # Hậu kiểm bảng school_id không có school_year_id:
    # chỉ PAST hoặc audit log được phép còn ở source.
    move_year_set = set(move_year_ids)
    for table in _no_year_school_tables(con):
        if (
            table == "users"
            or table in MERGER_AUDIT_TABLES
            or table in AUDIT_NO_YEAR_TABLES
            or table.endswith("_logs")
        ):
            continue

        pk = _simple_pk(con, table)
        if pk is None:
            continue

        rows = con.execute(
            f"SELECT * FROM {_quote_ident(table)} "
            f"WHERE school_id IN ({_markers(len(source_ids))}) "
            f"ORDER BY {_quote_ident(pk)}",
            source_ids,
        ).fetchall()

        residual_current_future = 0
        unresolved_after = 0

        for row in rows:
            year_id, _ = _resolve_indirect_year(
                con,
                table,
                row,
            )
            if year_id is None:
                unresolved_after += 1
            elif int(year_id) in move_year_set:
                residual_current_future += 1

        if unresolved_after:
            raise SchoolMergerError(
                f"Sau sáp nhập {table} còn {unresolved_after} dòng "
                "không truy được năm học tại source."
            )

        if residual_current_future:
            raise SchoolMergerError(
                f"Sau sáp nhập {table} còn "
                f"{residual_current_future} dòng CURRENT/FUTURE "
                "tại source."
            )

    if _table_exists(con, "users"):
        n = int(con.execute(
            f"SELECT COUNT(*) FROM users WHERE school_id IN ({_markers(len(source_ids))}) "
            "AND username NOT LIKE 'truong_%'",
            source_ids,
        ).fetchone()[0] or 0)
        if n:
            raise SchoolMergerError(f"Sau sáp nhập vẫn còn {n} tài khoản CBQL/GV/khác ở trường nguồn.")
        active_source_logins = int(con.execute(
            f"SELECT COUNT(*) FROM users WHERE school_id IN ({_markers(len(source_ids))}) "
            "AND username LIKE 'truong_%' AND is_active=1",
            source_ids,
        ).fetchone()[0] or 0)
        if active_source_logins:
            raise SchoolMergerError("Vẫn còn tài khoản Trường nguồn đang hoạt động sau sáp nhập.")
        target_logins = int(con.execute(
            "SELECT COUNT(*) FROM users WHERE school_id=? AND username LIKE 'truong_%' AND is_active=1",
            (target_school_id,),
        ).fetchone()[0] or 0)
        if target_logins != 1:
            raise SchoolMergerError(
                f"Sau sáp nhập trường đích không còn đúng 1 tài khoản Trường gốc active (hiện {target_logins})."
            )

    fk_errors = con.execute("PRAGMA foreign_key_check").fetchall()
    if fk_errors:
        raise SchoolMergerError(f"foreign_key_check phát hiện {len(fk_errors)} lỗi.")
    integrity = str(con.execute("PRAGMA integrity_check").fetchone()[0])
    if integrity.lower() != "ok":
        raise SchoolMergerError(f"integrity_check sau thao tác: {integrity}")

    if record_audit:
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
            "INSERT INTO school_merger_operations ("
            "school_year_id,target_school_id,source_school_ids_json,actor_user_id,"
            "backup_name,summary_json,created_at) VALUES (?,?,?,?,?,?,?)",
            (
                selected_year_id,
                target_school_id,
                json.dumps(source_ids, ensure_ascii=False),
                actor_user_id,
                backup_name,
                json.dumps(result, ensure_ascii=False),
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )

    return result


def _fingerprint_payload(preview: dict[str, Any]) -> str:
    stable = {
        "year_id": preview.get("selected_year", {}).get("id"),
        "target": preview.get("target_school", {}).get("id"),
        "sources": [x.get("id") for x in preview.get("source_schools", [])],
        "approved_plan": {
            "id": (preview.get("approved_plan") or {}).get("id"),
            "document_code": (preview.get("approved_plan") or {}).get("document_code"),
            "status": (preview.get("approved_plan") or {}).get("status"),
        },
        "inventory": preview.get("inventory"),
        "safe": preview.get("safe_to_execute"),
    }
    raw = json.dumps(stable, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def build_preview(
    *,
    selected_year_id: int,
    target_school_id: int,
    source_ids: list[int],
    require_active_sources: bool = True,
) -> dict[str, Any]:
    source_ids = sorted(set(int(x) for x in source_ids if int(x) != target_school_id))
    with _connect(read_only=True) as con:
        integrity = str(con.execute("PRAGMA integrity_check").fetchone()[0])
        previous_year_id = _previous_year_id(con, selected_year_id)
        target, sources, blockers, warnings = _validate_selection(
            con,
            selected_year_id=selected_year_id,
            target_school_id=target_school_id,
            source_ids=source_ids,
            require_active_sources=require_active_sources,
        )
        approved_plan, plan_blockers, plan_warnings = _validate_plan_gate(
            selected_year_id=selected_year_id,
            target_school_id=target_school_id,
            source_ids=source_ids,
        )
        blockers.extend(plan_blockers)
        warnings.extend(plan_warnings)
        if integrity.lower() != "ok":
            blockers.append(f"Database không đạt integrity_check: {integrity}")

        years = _school_year_rows(con)
        selected_year = next(
            (x for x in years if int(x["id"]) == selected_year_id),
            {"id": selected_year_id, "code": "", "name": ""},
        )
        previous_year = next(
            (x for x in years if previous_year_id is not None and int(x["id"]) == previous_year_id),
            None,
        )

        inventory = _preview_inventory(
            con,
            selected_year_id=selected_year_id,
            previous_year_id=previous_year_id,
            target_school_id=target_school_id,
            source_ids=source_ids,
        ) if target and sources else {
            "direct_rows": [], "historical_total": 0, "users_total": 0,
            "source_school_logins_disable": 0, "users_move_target": 0,
            "staff_rollover_candidates": 0, "staff_existing_elsewhere": 0,
            "staff_previous_duplicates": 0, "staff_unclassified": 0,
            "no_year_rows": [], "no_year_blockers": [],
        }

        blockers.extend(inventory.get("no_year_blockers") or [])
        if inventory.get("staff_previous_duplicates"):
            blockers.append(
                f"Đội ngũ năm trước có {inventory['staff_previous_duplicates']} staff_member_id trùng trong nhóm gộp."
            )
        if inventory.get("staff_unclassified"):
            blockers.append(
                f"Có {inventory['staff_unclassified']} hồ sơ đội ngũ năm trước chưa phân loại được."
            )
        if previous_year_id is None and _table_exists(con, "staff_year_records"):
            warnings.append("Không xác định được năm học liền trước; nhánh rollover đội ngũ sẽ không chạy.")
        if inventory.get("staff_existing_elsewhere"):
            warnings.append(
                f"Có {inventory['staff_existing_elsewhere']} nhân sự đã có hồ sơ năm hiện hành ở trường khác; sẽ giữ nguyên trường đó, không clone về trường đích."
            )

        simulation_result = None
        simulation_error = ""
        if not blockers and target and sources:
            try:
                mem = sqlite3.connect(":memory:")
                mem.row_factory = sqlite3.Row
                con.backup(mem)
                mem.execute("PRAGMA foreign_keys=ON")
                mem.execute("BEGIN")
                simulation_result = _apply_merge(
                    mem,
                    selected_year_id=selected_year_id,
                    previous_year_id=previous_year_id,
                    target_school_id=target_school_id,
                    source_ids=source_ids,
                    actor_user_id=None,
                    record_audit=False,
                )
                mem.rollback()
                mem.close()
            except Exception as exc:
                try:
                    mem.close()
                except Exception:
                    pass
                simulation_error = str(exc)
                blockers.append("Mô phỏng trên bản sao database thất bại: " + simulation_error)

        preview = {
            "selected_year": selected_year,
            "previous_year": previous_year,
            "approved_plan": approved_plan,
            "target_school": target,
            "source_schools": sources,
            "inventory": inventory,
            "warnings": warnings,
            "blockers": blockers,
            "simulation_result": simulation_result,
            "simulation_error": simulation_error,
            "safe_to_execute": not blockers and simulation_result is not None,
            "confirm_phrase": CONFIRM_PHRASE,
        }
        preview["fingerprint"] = _fingerprint_payload(preview)
        return preview


def _backup_database(
    *,
    selected_year_id: int,
    target_school_id: int,
    source_ids: list[int],
    actor: dict[str, Any],
) -> tuple[Path, str]:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    folder = EXPORT_DIR / f"backup_truoc_sap_nhap_{stamp}"
    folder.mkdir(parents=True, exist_ok=False)
    db_target = folder / "phocap.db"

    src = sqlite3.connect(str(DATABASE_PATH), timeout=30)
    dst = sqlite3.connect(str(db_target), timeout=30)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()

    chk = sqlite3.connect(str(db_target), timeout=30)
    try:
        integrity = str(chk.execute("PRAGMA integrity_check").fetchone()[0])
        fk = chk.execute("PRAGMA foreign_key_check").fetchall()
        if integrity.lower() != "ok" or fk:
            raise SchoolMergerError(
                f"Backup trước sáp nhập không đạt kiểm tra: integrity={integrity}; fk={len(fk)}"
            )
    finally:
        chk.close()

    meta = {
        "backup_type": "automatic_before_school_merger",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "school_year_id": selected_year_id,
        "target_school_id": target_school_id,
        "source_school_ids": source_ids,
        "actor": {
            "id": actor.get("id"),
            "username": actor.get("username"),
            "full_name": actor.get("full_name"),
            "role_code": actor.get("role_code"),
        },
        "database_backup": str(db_target),
    }
    (folder / "thong_tin_sap_nhap.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return folder, folder.name


def execute_merge(
    *,
    selected_year_id: int,
    target_school_id: int,
    source_ids: list[int],
    actor: dict[str, Any],
    expected_fingerprint: str,
) -> dict[str, Any]:
    # Lặp lại toàn bộ preview ngay trước backup để khóa trạng thái.
    preview = build_preview(
        selected_year_id=selected_year_id,
        target_school_id=target_school_id,
        source_ids=source_ids,
        require_active_sources=True,
    )
    if not preview["safe_to_execute"]:
        raise SchoolMergerError(
            "Kế hoạch không còn an toàn: " + " | ".join(preview.get("blockers") or [])
        )
    if not expected_fingerprint or expected_fingerprint != preview["fingerprint"]:
        raise SchoolMergerError(
            "Dữ liệu/kế hoạch đã thay đổi từ lúc xem trước. Hãy bấm Xem trước lại trước khi thực hiện."
        )

    source_ids = sorted(set(int(x) for x in source_ids if int(x) != target_school_id))
    backup_dir, backup_name = _backup_database(
        selected_year_id=selected_year_id,
        target_school_id=target_school_id,
        source_ids=source_ids,
        actor=actor,
    )

    con = _connect(read_only=False)
    committed = False
    try:
        con.execute("BEGIN IMMEDIATE")
        previous_year_id = _previous_year_id(con, selected_year_id)
        result = _apply_merge(
            con,
            selected_year_id=selected_year_id,
            previous_year_id=previous_year_id,
            target_school_id=target_school_id,
            source_ids=source_ids,
            actor_user_id=int(actor["id"]) if actor.get("id") is not None else None,
            backup_name=backup_name,
            record_audit=True,
        )
        con.commit()
        committed = True

        integrity = str(con.execute("PRAGMA integrity_check").fetchone()[0])
        fk = con.execute("PRAGMA foreign_key_check").fetchall()
        if integrity.lower() != "ok" or fk:
            raise SchoolMergerError(
                "Đã commit nhưng kiểm tra sau commit không đạt. "
                f"Hãy dùng backup {backup_name}. integrity={integrity}; fk={len(fk)}"
            )
    except Exception:
        if not committed:
            try:
                con.rollback()
            except Exception:
                pass
        raise
    finally:
        con.close()

    report_dir = EXPORT_DIR / (
        "sap_nhap_truong_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    )
    report_dir.mkdir(parents=True, exist_ok=False)
    payload = {
        "status": "SUCCESS",
        "school_year_id": selected_year_id,
        "target_school_id": target_school_id,
        "source_school_ids": source_ids,
        "backup_name": backup_name,
        "actor": actor,
        "result": result,
        "completed_at": datetime.now().isoformat(timespec="seconds"),
    }
    (report_dir / "ket_qua_sap_nhap.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )

    return {
        "backup_name": backup_name,
        "backup_dir": str(backup_dir),
        "report_dir": str(report_dir),
        "result": result,
    }


def merger_history(limit: int = 20) -> list[dict[str, Any]]:
    with _connect(read_only=True) as con:
        if not _table_exists(con, "school_merger_operations"):
            return []
        rows = con.execute(
            "SELECT id,school_year_id,target_school_id,source_school_ids_json,"
            "actor_user_id,backup_name,summary_json,created_at "
            "FROM school_merger_operations ORDER BY id DESC LIMIT ?",
            (int(limit),),
        ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            try:
                item["source_school_ids"] = json.loads(item.pop("source_school_ids_json"))
            except Exception:
                item["source_school_ids"] = []
            try:
                item["summary"] = json.loads(item.pop("summary_json"))
            except Exception:
                item["summary"] = {}
            result.append(item)
        return result
