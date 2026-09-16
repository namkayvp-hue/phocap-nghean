# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates


ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "phocap.db"
BACKUP_DIR = ROOT / "backups"
TEMPLATE_DIR = ROOT / "app" / "templates"

CURRENT_YEAR_ID = 2
BASE_YEAR_ID = 1
MANUAL_SPLIT_SOURCE_IDS = {1510, 1522, 1658}

router = APIRouter(prefix="/mang-luoi-hien-hanh", tags=["Mạng lưới hiện hành"])
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

FIELD_LABELS = {
    "school_count": "Số trường",
    "class_total": "Tổng số lớp",
    "student_total": "Tổng số học sinh",
    "new_students": "Học sinh tuyển mới",
    "new_student_total": "Học sinh tuyển mới",
    "staff_total": "Tổng đội ngũ",
    "management_total": "CBQL",
    "manager_total": "CBQL",
    "teachers": "Giáo viên",
    "teacher_total": "Giáo viên",
    "teacher_team": "Tổ/nhóm chuyên môn",
    "employees_total": "Nhân viên",
    "employee_total": "Nhân viên",
    "rooms_total": "Tổng số phòng học",
    "classroom_total": "Tổng số phòng học",
    "rooms_permanent": "Phòng kiên cố",
    "room_permanent": "Phòng kiên cố",
    "rooms_semi_permanent": "Phòng bán kiên cố",
    "room_semi_permanent": "Phòng bán kiên cố",
    "rooms_temporary": "Phòng tạm",
    "room_temporary": "Phòng tạm",
    "national_standard": "Trường đạt chuẩn quốc gia",
    "national_standard_count": "Số trường đạt chuẩn quốc gia",
    "class_24_36m": "Nhóm 24-36 tháng",
    "class_3_4y": "Lớp 3-4 tuổi",
    "class_4_5y": "Lớp 4-5 tuổi",
    "class_5_6y": "Lớp 5-6 tuổi",
    "student_12_24m": "Trẻ 12-24 tháng",
    "student_24_36m": "Trẻ 24-36 tháng",
    "student_3_4y": "Trẻ 3-4 tuổi",
    "student_4_5y": "Trẻ 4-5 tuổi",
    "student_5_6y": "Trẻ 5-6 tuổi",
}

LEVEL_LABELS = {"MN": "Mầm non", "TH": "Tiểu học", "THCS": "THCS", "THPT": "THPT"}


def _conn() -> sqlite3.Connection:
    con = sqlite3.connect(str(DB_PATH), timeout=60)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    return con


def _table_columns(con: sqlite3.Connection, table: str) -> set[str]:
    return {str(r[1]) for r in con.execute(f'PRAGMA table_info("{table}")').fetchall()}


def _actor(request: Request) -> dict[str, Any] | None:
    uid = request.session.get("user_id")
    if not uid:
        return None

    with _conn() as con:
        ucols = _table_columns(con, "users")
        if "id" not in ucols:
            return None

        row = con.execute("SELECT * FROM users WHERE id=?", (int(uid),)).fetchone()
        if row is None:
            return None

        user = dict(row)
        if "is_active" in user and not bool(user.get("is_active")):
            return None

        role_code = ""
        if "role_code" in user and user.get("role_code"):
            role_code = str(user.get("role_code") or "")
        elif "role_id" in user and user.get("role_id") is not None:
            try:
                rcols = _table_columns(con, "roles")
                rrow = con.execute("SELECT * FROM roles WHERE id=?", (int(user["role_id"]),)).fetchone()
                if rrow:
                    rd = dict(rrow)
                    for key in ("code", "role_code", "name"):
                        if key in rcols and rd.get(key):
                            role_code = str(rd[key])
                            break
            except Exception:
                role_code = ""

        role_norm = role_code.strip().upper()
        username = str(user.get("username") or "").strip().lower()

        scope = "DENY"
        if any(x in role_norm for x in ("GV", "TEACHER")):
            scope = "DENY"
        elif any(x in role_norm for x in ("SO", "ADMIN", "PROVINCE", "SOGDDT")) or username.startswith("admin."):
            scope = "PROVINCE"
        elif any(x in role_norm for x in ("XA", "COMMUNE")):
            scope = "COMMUNE"
        elif any(x in role_norm for x in ("TRUONG", "SCHOOL")):
            scope = "SCHOOL"

        return {
            "id": int(user["id"]),
            "username": username,
            "full_name": str(user.get("full_name") or user.get("name") or username),
            "role_code": role_code,
            "scope": scope,
            "commune_id": int(user["commune_id"]) if user.get("commune_id") is not None else None,
            "school_id": int(user["school_id"]) if user.get("school_id") is not None else None,
        }


def _official_target_ids(con: sqlite3.Connection) -> set[int]:
    rows = con.execute(
        """
        SELECT DISTINCT target_school_id
        FROM school_merger_official_executions
        WHERE school_year_id=?
          AND target_school_id IS NOT NULL
        """,
        (CURRENT_YEAR_ID,),
    ).fetchall()
    return {int(r[0]) for r in rows}


def _source_ids(con: sqlite3.Connection, target_school_id: int) -> list[int]:
    rows = con.execute(
        """
        SELECT source_school_ids_json
        FROM school_merger_official_executions
        WHERE school_year_id=? AND target_school_id=?
        ORDER BY id
        """,
        (CURRENT_YEAR_ID, target_school_id),
    ).fetchall()

    result: list[int] = []
    for r in rows:
        try:
            values = json.loads(r[0] or "[]")
        except Exception:
            values = []
        for value in values:
            try:
                sid = int(value)
            except Exception:
                continue
            if sid not in result:
                result.append(sid)
    return result


def _school_allowed(con: sqlite3.Connection, actor: dict[str, Any], school_id: int) -> bool:
    if school_id not in _official_target_ids(con):
        return False
    if school_id in MANUAL_SPLIT_SOURCE_IDS:
        return False

    row = con.execute(
        "SELECT id,commune_id,is_active FROM schools WHERE id=?",
        (school_id,),
    ).fetchone()
    if row is None or not bool(row["is_active"]):
        return False

    if actor["scope"] == "PROVINCE":
        return True
    if actor["scope"] == "COMMUNE":
        return actor.get("commune_id") is not None and int(row["commune_id"]) == int(actor["commune_id"])
    if actor["scope"] == "SCHOOL":
        return actor.get("school_id") is not None and int(school_id) == int(actor["school_id"])
    return False


def _schools_for_actor(con: sqlite3.Connection, actor: dict[str, Any], commune_id: int | None):
    targets = sorted(_official_target_ids(con))
    if not targets:
        return []

    placeholders = ",".join("?" for _ in targets)
    sql = f"""
        SELECT s.id,s.code,s.name,s.commune_id,c.name AS commune_name,s.is_active
        FROM schools s
        LEFT JOIN communes c ON c.id=s.commune_id
        WHERE s.id IN ({placeholders})
          AND s.is_active=1
    """
    params: list[Any] = list(targets)

    if actor["scope"] == "COMMUNE":
        sql += " AND s.commune_id=?"
        params.append(int(actor["commune_id"]))
    elif actor["scope"] == "SCHOOL":
        sql += " AND s.id=?"
        params.append(int(actor["school_id"]))
    elif actor["scope"] == "PROVINCE" and commune_id:
        sql += " AND s.commune_id=?"
        params.append(int(commune_id))

    sql += " ORDER BY c.name,s.name"
    return [dict(r) for r in con.execute(sql, tuple(params)).fetchall()]


def _communes(con: sqlite3.Connection, actor: dict[str, Any]):
    if actor["scope"] != "PROVINCE":
        return []
    return [
        dict(r) for r in con.execute(
            "SELECT id,code,name FROM communes WHERE is_active=1 ORDER BY name"
        ).fetchall()
    ]


def _levels_for_school(con: sqlite3.Connection, school_id: int) -> list[str]:
    ids = [school_id] + _source_ids(con, school_id)
    placeholders = ",".join("?" for _ in ids)
    rows = con.execute(
        f"""
        SELECT DISTINCT UPPER(TRIM(level_code))
        FROM school_network_year_data
        WHERE school_id IN ({placeholders})
          AND school_year_id IN (?,?)
          AND TRIM(COALESCE(level_code,''))<>''
        ORDER BY 1
        """,
        tuple(ids) + (BASE_YEAR_ID, CURRENT_YEAR_ID),
    ).fetchall()
    return [str(r[0]) for r in rows if str(r[0]) in LEVEL_LABELS]


def _row_json(con: sqlite3.Connection, school_id: int, year_id: int, level: str):
    row = con.execute(
        """
        SELECT id,data_json,source_name,imported_at
        FROM school_network_year_data
        WHERE school_id=? AND school_year_id=? AND UPPER(TRIM(level_code))=?
        ORDER BY id DESC
        LIMIT 1
        """,
        (school_id, year_id, level),
    ).fetchone()
    if row is None:
        return None

    try:
        payload = json.loads(row["data_json"] or "{}")
        if not isinstance(payload, dict):
            payload = {}
    except Exception:
        payload = {}

    return {
        "id": int(row["id"]),
        "data": payload,
        "source_name": row["source_name"],
        "imported_at": row["imported_at"],
    }


def _reference(con: sqlite3.Connection, target_school_id: int, level: str):
    component_ids = [target_school_id] + _source_ids(con, target_school_id)
    result = []
    keys: set[str] = set()

    for sid in component_ids:
        srow = con.execute("SELECT id,code,name FROM schools WHERE id=?", (sid,)).fetchone()
        r = _row_json(con, sid, BASE_YEAR_ID, level)
        if r is None:
            continue
        keys.update(str(k) for k in r["data"].keys())
        result.append({
            "school_id": sid,
            "school_code": srow["code"] if srow else "",
            "school_name": srow["name"] if srow else f"school_id={sid}",
            "data": r["data"],
        })

    return sorted(keys), result


def _value_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "1" if value else "0"
    return str(value)


def _parse_value(raw: str) -> Any:
    text = str(raw or "").strip()
    if text == "":
        return None

    low = text.lower()
    if low in {"null", "none", "khong_xac_dinh", "không xác định", "chua_xac_dinh", "chưa xác định"}:
        return None
    if low in {"true", "co", "có", "yes"}:
        return 1
    if low in {"false", "khong", "không", "no"}:
        return 0

    try:
        if _is_int(text):
            return int(text)
        return float(text.replace(",", "."))
    except Exception:
        return text


def _is_int(text: str) -> bool:
    if not text:
        return False
    if text[0] in "+-":
        return text[1:].isdigit()
    return text.isdigit()


def _state_hash(current_row, keys, reference_rows) -> str:
    payload = {"current": current_row, "keys": keys, "reference": reference_rows}
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _backup_db() -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    path = BACKUP_DIR / f"backup_truoc_luu_mang_luoi_hien_hanh_{ts}.db"

    src = sqlite3.connect(str(DB_PATH), timeout=60)
    dst = sqlite3.connect(str(path), timeout=60)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()

    chk = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=30)
    try:
        if chk.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("Backup database không đạt integrity_check.")
        if chk.execute("PRAGMA foreign_key_check").fetchall():
            raise RuntimeError("Backup database có lỗi foreign key.")
    finally:
        chk.close()

    return path


@router.get("")
def network_current_page(
    request: Request,
    commune_id: str | None = None,
    school_id: str | None = None,
    level: str | None = None,
    status: str | None = None,
):
    actor = _actor(request)
    if actor is None or actor["scope"] == "DENY":
        return RedirectResponse(url="/", status_code=303)

    def _optional_positive_int(value):
        text = str(value or "").strip()
        if not text:
            return None
        try:
            number = int(text)
        except Exception:
            return None
        return number if number > 0 else None

    commune_id_int = _optional_positive_int(commune_id)
    school_id_int = _optional_positive_int(school_id)

    with _conn() as con:
        communes = _communes(con, actor)
        schools = _schools_for_actor(con, actor, commune_id_int)

        selected_school = None
        if school_id_int is not None and _school_allowed(con, actor, school_id_int):
            selected_school = next((x for x in schools if int(x["id"]) == school_id_int), None)

        if actor["scope"] == "SCHOOL" and actor.get("school_id"):
            sid = int(actor["school_id"])
            if _school_allowed(con, actor, sid):
                selected_school = next((x for x in schools if int(x["id"]) == sid), None)
                school_id_int = sid

        levels = _levels_for_school(con, school_id_int) if selected_school and school_id_int is not None else []
        selected_level = str(level or "").strip().upper()
        if selected_level not in levels:
            selected_level = levels[0] if len(levels) == 1 else ""

        keys: list[str] = []
        reference_rows = []
        current = None
        state_hash = ""

        if selected_school and selected_level:
            keys, reference_rows = _reference(con, int(school_id), selected_level)
            current = _row_json(con, int(school_id), CURRENT_YEAR_ID, selected_level)
            if current:
                keys = sorted(set(keys) | {str(k) for k in current["data"].keys()})
            state_hash = _state_hash(current, keys, reference_rows)

        missing_target_ids = []
        for s in schools:
            sid = int(s["id"])
            levels_s = _levels_for_school(con, sid)
            if not levels_s:
                continue
            if any(_row_json(con, sid, CURRENT_YEAR_ID, lv) is None for lv in levels_s):
                missing_target_ids.append(sid)

        fields = []
        if selected_school and selected_level:
            current_data = current["data"] if current else {}
            for key in keys:
                refs = []
                for rr in reference_rows:
                    refs.append({
                        "school_id": rr["school_id"],
                        "school_name": rr["school_name"],
                        "value": rr["data"].get(key),
                    })
                fields.append({
                    "key": key,
                    "label": FIELD_LABELS.get(key, key),
                    "current_value": _value_text(current_data.get(key)),
                    "references": refs,
                })

        return templates.TemplateResponse(
            request=request,
            name="report_inputs/network_current.html",
            context={
                "actor": actor,
                "communes": communes,
                "schools": schools,
                "selected_commune_id": commune_id_int,
                "selected_school": selected_school,
                "selected_school_id": school_id_int,
                "levels": levels,
                "selected_level": selected_level,
                "level_labels": LEVEL_LABELS,
                "fields": fields,
                "current": current,
                "state_hash": state_hash,
                "status": status,
                "missing_target_ids": missing_target_ids,
                "missing_count": len(missing_target_ids),
                "year_label": "2026-2027",
                "base_year_label": "2025-2026",
            },
        )


@router.post("/luu")
async def network_current_save(request: Request):
    actor = _actor(request)
    if actor is None or actor["scope"] == "DENY":
        return RedirectResponse(url="/", status_code=303)

    form = await request.form()

    try:
        school_id = int(str(form.get("school_id") or "").strip())
    except Exception:
        return RedirectResponse(url="/mang-luoi-hien-hanh?status=invalid_school", status_code=303)

    level = str(form.get("level") or "").strip().upper()
    state_hash = str(form.get("state_hash") or "").strip()

    if level not in LEVEL_LABELS:
        return RedirectResponse(
            url=f"/mang-luoi-hien-hanh?school_id={school_id}&status=invalid_level",
            status_code=303,
        )

    with _conn() as con:
        if not _school_allowed(con, actor, school_id):
            return RedirectResponse(url="/mang-luoi-hien-hanh?status=forbidden", status_code=303)

        levels = _levels_for_school(con, school_id)
        if level not in levels:
            return RedirectResponse(
                url=f"/mang-luoi-hien-hanh?school_id={school_id}&status=level_not_allowed",
                status_code=303,
            )

        keys, reference_rows = _reference(con, school_id, level)
        current = _row_json(con, school_id, CURRENT_YEAR_ID, level)
        if current:
            keys = sorted(set(keys) | {str(k) for k in current["data"].keys()})

        expected_hash = _state_hash(current, keys, reference_rows)
        if not state_hash or state_hash != expected_hash:
            return RedirectResponse(
                url=f"/mang-luoi-hien-hanh?school_id={school_id}&level={level}&status=stale",
                status_code=303,
            )

        new_data: dict[str, Any] = {}
        for key in keys:
            new_data[key] = _parse_value(str(form.get(f"field__{key}") or ""))

        if not any(v is not None for v in new_data.values()):
            return RedirectResponse(
                url=f"/mang-luoi-hien-hanh?school_id={school_id}&level={level}&status=empty",
                status_code=303,
            )

    _backup_db()

    con = _conn()
    try:
        con.execute("BEGIN IMMEDIATE")

        if not _school_allowed(con, actor, school_id):
            raise RuntimeError("Phạm vi trường thay đổi trước khi ghi.")

        existing = con.execute(
            """
            SELECT id
            FROM school_network_year_data
            WHERE school_id=? AND school_year_id=? AND UPPER(TRIM(level_code))=?
            ORDER BY id DESC
            LIMIT 1
            """,
            (school_id, CURRENT_YEAR_ID, level),
        ).fetchone()

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
        payload = json.dumps(new_data, ensure_ascii=False, separators=(",", ":"))
        source_name = "Nhập/cập nhật thủ công sau sáp nhập - Mạng lưới hiện hành 2026-2027"

        if existing is None:
            con.execute(
                """
                INSERT INTO school_network_year_data
                (school_id,school_year_id,level_code,data_json,source_name,imported_at)
                VALUES (?,?,?,?,?,?)
                """,
                (school_id, CURRENT_YEAR_ID, level, payload, source_name, now),
            )
        else:
            con.execute(
                """
                UPDATE school_network_year_data
                SET data_json=?,source_name=?,imported_at=?
                WHERE id=?
                """,
                (payload, source_name, now, int(existing["id"])),
            )

        if con.execute("PRAGMA foreign_key_check").fetchall():
            raise RuntimeError("Foreign key check không đạt.")

        row = con.execute(
            """
            SELECT data_json
            FROM school_network_year_data
            WHERE school_id=? AND school_year_id=? AND UPPER(TRIM(level_code))=?
            ORDER BY id DESC
            LIMIT 1
            """,
            (school_id, CURRENT_YEAR_ID, level),
        ).fetchone()
        if row is None or json.loads(row["data_json"] or "{}") != new_data:
            raise RuntimeError("Post-check dữ liệu mạng lưới không khớp.")

        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()

    return RedirectResponse(
        url=f"/mang-luoi-hien-hanh?school_id={school_id}&level={level}&status=saved",
        status_code=303,
    )
