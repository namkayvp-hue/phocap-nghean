# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import py_compile
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(r"C:\PhoCap")
DB = ROOT / "data" / "phocap.db"
APP = ROOT / "app"
ROUTERS = APP / "routers"
TEMPLATES = APP / "templates" / "report_inputs"
MAIN = APP / "main.py"

ROUTER_FILE = ROUTERS / "network_current.py"
TEMPLATE_FILE = TEMPLATES / "network_current.html"

EXPORT_DIR = ROOT / "exports"
BACKUP_DIR = ROOT / "backups"
OUT = EXPORT_DIR / "BATCH_CAI_DAT_MANG_LUOI_HIEN_HANH_18.txt"

EXPECTED_DB_SHA = "2a43e36ff8f192abb46668faa1366ed7242984bfd876f90572cd83b90ee7837e"

MARKER_START = "# === BATCH18_NETWORK_CURRENT_START ==="
MARKER_END = "# === BATCH18_NETWORK_CURRENT_END ==="

ROUTER_CODE = '# -*- coding: utf-8 -*-\nfrom __future__ import annotations\n\nimport hashlib\nimport json\nimport sqlite3\nfrom datetime import datetime\nfrom pathlib import Path\nfrom typing import Any\n\nfrom fastapi import APIRouter, Request\nfrom fastapi.responses import RedirectResponse\nfrom fastapi.templating import Jinja2Templates\n\n\nROOT = Path(__file__).resolve().parents[2]\nDB_PATH = ROOT / "data" / "phocap.db"\nBACKUP_DIR = ROOT / "backups"\nTEMPLATE_DIR = ROOT / "app" / "templates"\n\nCURRENT_YEAR_ID = 2\nBASE_YEAR_ID = 1\nMANUAL_SPLIT_SOURCE_IDS = {1510, 1522, 1658}\n\nrouter = APIRouter(prefix="/mang-luoi-hien-hanh", tags=["Mạng lưới hiện hành"])\ntemplates = Jinja2Templates(directory=str(TEMPLATE_DIR))\n\nFIELD_LABELS = {\n    "school_count": "Số trường",\n    "class_total": "Tổng số lớp",\n    "student_total": "Tổng số học sinh",\n    "new_students": "Học sinh tuyển mới",\n    "new_student_total": "Học sinh tuyển mới",\n    "staff_total": "Tổng đội ngũ",\n    "management_total": "CBQL",\n    "manager_total": "CBQL",\n    "teachers": "Giáo viên",\n    "teacher_total": "Giáo viên",\n    "teacher_team": "Tổ/nhóm chuyên môn",\n    "employees_total": "Nhân viên",\n    "employee_total": "Nhân viên",\n    "rooms_total": "Tổng số phòng học",\n    "classroom_total": "Tổng số phòng học",\n    "rooms_permanent": "Phòng kiên cố",\n    "room_permanent": "Phòng kiên cố",\n    "rooms_semi_permanent": "Phòng bán kiên cố",\n    "room_semi_permanent": "Phòng bán kiên cố",\n    "rooms_temporary": "Phòng tạm",\n    "room_temporary": "Phòng tạm",\n    "national_standard": "Trường đạt chuẩn quốc gia",\n    "national_standard_count": "Số trường đạt chuẩn quốc gia",\n    "class_24_36m": "Nhóm 24-36 tháng",\n    "class_3_4y": "Lớp 3-4 tuổi",\n    "class_4_5y": "Lớp 4-5 tuổi",\n    "class_5_6y": "Lớp 5-6 tuổi",\n    "student_12_24m": "Trẻ 12-24 tháng",\n    "student_24_36m": "Trẻ 24-36 tháng",\n    "student_3_4y": "Trẻ 3-4 tuổi",\n    "student_4_5y": "Trẻ 4-5 tuổi",\n    "student_5_6y": "Trẻ 5-6 tuổi",\n}\n\nLEVEL_LABELS = {"MN": "Mầm non", "TH": "Tiểu học", "THCS": "THCS", "THPT": "THPT"}\n\n\ndef _conn() -> sqlite3.Connection:\n    con = sqlite3.connect(str(DB_PATH), timeout=60)\n    con.row_factory = sqlite3.Row\n    con.execute("PRAGMA foreign_keys=ON")\n    return con\n\n\ndef _table_columns(con: sqlite3.Connection, table: str) -> set[str]:\n    return {str(r[1]) for r in con.execute(f\'PRAGMA table_info("{table}")\').fetchall()}\n\n\ndef _actor(request: Request) -> dict[str, Any] | None:\n    uid = request.session.get("user_id")\n    if not uid:\n        return None\n\n    with _conn() as con:\n        ucols = _table_columns(con, "users")\n        if "id" not in ucols:\n            return None\n\n        row = con.execute("SELECT * FROM users WHERE id=?", (int(uid),)).fetchone()\n        if row is None:\n            return None\n\n        user = dict(row)\n        if "is_active" in user and not bool(user.get("is_active")):\n            return None\n\n        role_code = ""\n        if "role_code" in user and user.get("role_code"):\n            role_code = str(user.get("role_code") or "")\n        elif "role_id" in user and user.get("role_id") is not None:\n            try:\n                rcols = _table_columns(con, "roles")\n                rrow = con.execute("SELECT * FROM roles WHERE id=?", (int(user["role_id"]),)).fetchone()\n                if rrow:\n                    rd = dict(rrow)\n                    for key in ("code", "role_code", "name"):\n                        if key in rcols and rd.get(key):\n                            role_code = str(rd[key])\n                            break\n            except Exception:\n                role_code = ""\n\n        role_norm = role_code.strip().upper()\n        username = str(user.get("username") or "").strip().lower()\n\n        scope = "DENY"\n        if any(x in role_norm for x in ("GV", "TEACHER")):\n            scope = "DENY"\n        elif any(x in role_norm for x in ("SO", "ADMIN", "PROVINCE", "SOGDDT")) or username.startswith("admin."):\n            scope = "PROVINCE"\n        elif any(x in role_norm for x in ("XA", "COMMUNE")):\n            scope = "COMMUNE"\n        elif any(x in role_norm for x in ("TRUONG", "SCHOOL")):\n            scope = "SCHOOL"\n\n        return {\n            "id": int(user["id"]),\n            "username": username,\n            "full_name": str(user.get("full_name") or user.get("name") or username),\n            "role_code": role_code,\n            "scope": scope,\n            "commune_id": int(user["commune_id"]) if user.get("commune_id") is not None else None,\n            "school_id": int(user["school_id"]) if user.get("school_id") is not None else None,\n        }\n\n\ndef _official_target_ids(con: sqlite3.Connection) -> set[int]:\n    rows = con.execute(\n        """\n        SELECT DISTINCT target_school_id\n        FROM school_merger_official_executions\n        WHERE school_year_id=?\n          AND target_school_id IS NOT NULL\n        """,\n        (CURRENT_YEAR_ID,),\n    ).fetchall()\n    return {int(r[0]) for r in rows}\n\n\ndef _source_ids(con: sqlite3.Connection, target_school_id: int) -> list[int]:\n    rows = con.execute(\n        """\n        SELECT source_school_ids_json\n        FROM school_merger_official_executions\n        WHERE school_year_id=? AND target_school_id=?\n        ORDER BY id\n        """,\n        (CURRENT_YEAR_ID, target_school_id),\n    ).fetchall()\n\n    result: list[int] = []\n    for r in rows:\n        try:\n            values = json.loads(r[0] or "[]")\n        except Exception:\n            values = []\n        for value in values:\n            try:\n                sid = int(value)\n            except Exception:\n                continue\n            if sid not in result:\n                result.append(sid)\n    return result\n\n\ndef _school_allowed(con: sqlite3.Connection, actor: dict[str, Any], school_id: int) -> bool:\n    if school_id not in _official_target_ids(con):\n        return False\n    if school_id in MANUAL_SPLIT_SOURCE_IDS:\n        return False\n\n    row = con.execute(\n        "SELECT id,commune_id,is_active FROM schools WHERE id=?",\n        (school_id,),\n    ).fetchone()\n    if row is None or not bool(row["is_active"]):\n        return False\n\n    if actor["scope"] == "PROVINCE":\n        return True\n    if actor["scope"] == "COMMUNE":\n        return actor.get("commune_id") is not None and int(row["commune_id"]) == int(actor["commune_id"])\n    if actor["scope"] == "SCHOOL":\n        return actor.get("school_id") is not None and int(school_id) == int(actor["school_id"])\n    return False\n\n\ndef _schools_for_actor(con: sqlite3.Connection, actor: dict[str, Any], commune_id: int | None):\n    targets = sorted(_official_target_ids(con))\n    if not targets:\n        return []\n\n    placeholders = ",".join("?" for _ in targets)\n    sql = f"""\n        SELECT s.id,s.code,s.name,s.commune_id,c.name AS commune_name,s.is_active\n        FROM schools s\n        LEFT JOIN communes c ON c.id=s.commune_id\n        WHERE s.id IN ({placeholders})\n          AND s.is_active=1\n    """\n    params: list[Any] = list(targets)\n\n    if actor["scope"] == "COMMUNE":\n        sql += " AND s.commune_id=?"\n        params.append(int(actor["commune_id"]))\n    elif actor["scope"] == "SCHOOL":\n        sql += " AND s.id=?"\n        params.append(int(actor["school_id"]))\n    elif actor["scope"] == "PROVINCE" and commune_id:\n        sql += " AND s.commune_id=?"\n        params.append(int(commune_id))\n\n    sql += " ORDER BY c.name,s.name"\n    return [dict(r) for r in con.execute(sql, tuple(params)).fetchall()]\n\n\ndef _communes(con: sqlite3.Connection, actor: dict[str, Any]):\n    if actor["scope"] != "PROVINCE":\n        return []\n    return [\n        dict(r) for r in con.execute(\n            "SELECT id,code,name FROM communes WHERE is_active=1 ORDER BY name"\n        ).fetchall()\n    ]\n\n\ndef _levels_for_school(con: sqlite3.Connection, school_id: int) -> list[str]:\n    ids = [school_id] + _source_ids(con, school_id)\n    placeholders = ",".join("?" for _ in ids)\n    rows = con.execute(\n        f"""\n        SELECT DISTINCT UPPER(TRIM(level_code))\n        FROM school_network_year_data\n        WHERE school_id IN ({placeholders})\n          AND school_year_id IN (?,?)\n          AND TRIM(COALESCE(level_code,\'\'))<>\'\'\n        ORDER BY 1\n        """,\n        tuple(ids) + (BASE_YEAR_ID, CURRENT_YEAR_ID),\n    ).fetchall()\n    return [str(r[0]) for r in rows if str(r[0]) in LEVEL_LABELS]\n\n\ndef _row_json(con: sqlite3.Connection, school_id: int, year_id: int, level: str):\n    row = con.execute(\n        """\n        SELECT id,data_json,source_name,imported_at\n        FROM school_network_year_data\n        WHERE school_id=? AND school_year_id=? AND UPPER(TRIM(level_code))=?\n        ORDER BY id DESC\n        LIMIT 1\n        """,\n        (school_id, year_id, level),\n    ).fetchone()\n    if row is None:\n        return None\n\n    try:\n        payload = json.loads(row["data_json"] or "{}")\n        if not isinstance(payload, dict):\n            payload = {}\n    except Exception:\n        payload = {}\n\n    return {\n        "id": int(row["id"]),\n        "data": payload,\n        "source_name": row["source_name"],\n        "imported_at": row["imported_at"],\n    }\n\n\ndef _reference(con: sqlite3.Connection, target_school_id: int, level: str):\n    component_ids = [target_school_id] + _source_ids(con, target_school_id)\n    result = []\n    keys: set[str] = set()\n\n    for sid in component_ids:\n        srow = con.execute("SELECT id,code,name FROM schools WHERE id=?", (sid,)).fetchone()\n        r = _row_json(con, sid, BASE_YEAR_ID, level)\n        if r is None:\n            continue\n        keys.update(str(k) for k in r["data"].keys())\n        result.append({\n            "school_id": sid,\n            "school_code": srow["code"] if srow else "",\n            "school_name": srow["name"] if srow else f"school_id={sid}",\n            "data": r["data"],\n        })\n\n    return sorted(keys), result\n\n\ndef _value_text(value: Any) -> str:\n    if value is None:\n        return ""\n    if isinstance(value, bool):\n        return "1" if value else "0"\n    return str(value)\n\n\ndef _parse_value(raw: str) -> Any:\n    text = str(raw or "").strip()\n    if text == "":\n        return None\n\n    low = text.lower()\n    if low in {"null", "none", "khong_xac_dinh", "không xác định", "chua_xac_dinh", "chưa xác định"}:\n        return None\n    if low in {"true", "co", "có", "yes"}:\n        return 1\n    if low in {"false", "khong", "không", "no"}:\n        return 0\n\n    try:\n        if _is_int(text):\n            return int(text)\n        return float(text.replace(",", "."))\n    except Exception:\n        return text\n\n\ndef _is_int(text: str) -> bool:\n    if not text:\n        return False\n    if text[0] in "+-":\n        return text[1:].isdigit()\n    return text.isdigit()\n\n\ndef _state_hash(current_row, keys, reference_rows) -> str:\n    payload = {"current": current_row, "keys": keys, "reference": reference_rows}\n    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)\n    return hashlib.sha256(raw.encode("utf-8")).hexdigest()\n\n\ndef _backup_db() -> Path:\n    BACKUP_DIR.mkdir(parents=True, exist_ok=True)\n    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")\n    path = BACKUP_DIR / f"backup_truoc_luu_mang_luoi_hien_hanh_{ts}.db"\n\n    src = sqlite3.connect(str(DB_PATH), timeout=60)\n    dst = sqlite3.connect(str(path), timeout=60)\n    try:\n        src.backup(dst)\n    finally:\n        dst.close()\n        src.close()\n\n    chk = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=30)\n    try:\n        if chk.execute("PRAGMA integrity_check").fetchone()[0] != "ok":\n            raise RuntimeError("Backup database không đạt integrity_check.")\n        if chk.execute("PRAGMA foreign_key_check").fetchall():\n            raise RuntimeError("Backup database có lỗi foreign key.")\n    finally:\n        chk.close()\n\n    return path\n\n\n@router.get("")\ndef network_current_page(\n    request: Request,\n    commune_id: int | None = None,\n    school_id: int | None = None,\n    level: str | None = None,\n    status: str | None = None,\n):\n    actor = _actor(request)\n    if actor is None or actor["scope"] == "DENY":\n        return RedirectResponse(url="/", status_code=303)\n\n    with _conn() as con:\n        communes = _communes(con, actor)\n        schools = _schools_for_actor(con, actor, commune_id)\n\n        selected_school = None\n        if school_id is not None and _school_allowed(con, actor, int(school_id)):\n            selected_school = next((x for x in schools if int(x["id"]) == int(school_id)), None)\n\n        if actor["scope"] == "SCHOOL" and actor.get("school_id"):\n            sid = int(actor["school_id"])\n            if _school_allowed(con, actor, sid):\n                selected_school = next((x for x in schools if int(x["id"]) == sid), None)\n                school_id = sid\n\n        levels = _levels_for_school(con, int(school_id)) if selected_school else []\n        selected_level = str(level or "").strip().upper()\n        if selected_level not in levels:\n            selected_level = levels[0] if len(levels) == 1 else ""\n\n        keys: list[str] = []\n        reference_rows = []\n        current = None\n        state_hash = ""\n\n        if selected_school and selected_level:\n            keys, reference_rows = _reference(con, int(school_id), selected_level)\n            current = _row_json(con, int(school_id), CURRENT_YEAR_ID, selected_level)\n            if current:\n                keys = sorted(set(keys) | {str(k) for k in current["data"].keys()})\n            state_hash = _state_hash(current, keys, reference_rows)\n\n        missing_target_ids = []\n        for s in schools:\n            sid = int(s["id"])\n            levels_s = _levels_for_school(con, sid)\n            if not levels_s:\n                continue\n            if any(_row_json(con, sid, CURRENT_YEAR_ID, lv) is None for lv in levels_s):\n                missing_target_ids.append(sid)\n\n        fields = []\n        if selected_school and selected_level:\n            current_data = current["data"] if current else {}\n            for key in keys:\n                refs = []\n                for rr in reference_rows:\n                    refs.append({\n                        "school_id": rr["school_id"],\n                        "school_name": rr["school_name"],\n                        "value": rr["data"].get(key),\n                    })\n                fields.append({\n                    "key": key,\n                    "label": FIELD_LABELS.get(key, key),\n                    "current_value": _value_text(current_data.get(key)),\n                    "references": refs,\n                })\n\n        return templates.TemplateResponse(\n            request=request,\n            name="report_inputs/network_current.html",\n            context={\n                "actor": actor,\n                "communes": communes,\n                "schools": schools,\n                "selected_commune_id": commune_id,\n                "selected_school": selected_school,\n                "selected_school_id": int(school_id) if school_id else None,\n                "levels": levels,\n                "selected_level": selected_level,\n                "level_labels": LEVEL_LABELS,\n                "fields": fields,\n                "current": current,\n                "state_hash": state_hash,\n                "status": status,\n                "missing_target_ids": missing_target_ids,\n                "missing_count": len(missing_target_ids),\n                "year_label": "2026-2027",\n                "base_year_label": "2025-2026",\n            },\n        )\n\n\n@router.post("/luu")\nasync def network_current_save(request: Request):\n    actor = _actor(request)\n    if actor is None or actor["scope"] == "DENY":\n        return RedirectResponse(url="/", status_code=303)\n\n    form = await request.form()\n\n    try:\n        school_id = int(str(form.get("school_id") or "").strip())\n    except Exception:\n        return RedirectResponse(url="/mang-luoi-hien-hanh?status=invalid_school", status_code=303)\n\n    level = str(form.get("level") or "").strip().upper()\n    state_hash = str(form.get("state_hash") or "").strip()\n\n    if level not in LEVEL_LABELS:\n        return RedirectResponse(\n            url=f"/mang-luoi-hien-hanh?school_id={school_id}&status=invalid_level",\n            status_code=303,\n        )\n\n    with _conn() as con:\n        if not _school_allowed(con, actor, school_id):\n            return RedirectResponse(url="/mang-luoi-hien-hanh?status=forbidden", status_code=303)\n\n        levels = _levels_for_school(con, school_id)\n        if level not in levels:\n            return RedirectResponse(\n                url=f"/mang-luoi-hien-hanh?school_id={school_id}&status=level_not_allowed",\n                status_code=303,\n            )\n\n        keys, reference_rows = _reference(con, school_id, level)\n        current = _row_json(con, school_id, CURRENT_YEAR_ID, level)\n        if current:\n            keys = sorted(set(keys) | {str(k) for k in current["data"].keys()})\n\n        expected_hash = _state_hash(current, keys, reference_rows)\n        if not state_hash or state_hash != expected_hash:\n            return RedirectResponse(\n                url=f"/mang-luoi-hien-hanh?school_id={school_id}&level={level}&status=stale",\n                status_code=303,\n            )\n\n        new_data: dict[str, Any] = {}\n        for key in keys:\n            new_data[key] = _parse_value(str(form.get(f"field__{key}") or ""))\n\n        if not any(v is not None for v in new_data.values()):\n            return RedirectResponse(\n                url=f"/mang-luoi-hien-hanh?school_id={school_id}&level={level}&status=empty",\n                status_code=303,\n            )\n\n    _backup_db()\n\n    con = _conn()\n    try:\n        con.execute("BEGIN IMMEDIATE")\n\n        if not _school_allowed(con, actor, school_id):\n            raise RuntimeError("Phạm vi trường thay đổi trước khi ghi.")\n\n        existing = con.execute(\n            """\n            SELECT id\n            FROM school_network_year_data\n            WHERE school_id=? AND school_year_id=? AND UPPER(TRIM(level_code))=?\n            ORDER BY id DESC\n            LIMIT 1\n            """,\n            (school_id, CURRENT_YEAR_ID, level),\n        ).fetchone()\n\n        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")\n        payload = json.dumps(new_data, ensure_ascii=False, separators=(",", ":"))\n        source_name = "Nhập/cập nhật thủ công sau sáp nhập - Mạng lưới hiện hành 2026-2027"\n\n        if existing is None:\n            con.execute(\n                """\n                INSERT INTO school_network_year_data\n                (school_id,school_year_id,level_code,data_json,source_name,imported_at)\n                VALUES (?,?,?,?,?,?)\n                """,\n                (school_id, CURRENT_YEAR_ID, level, payload, source_name, now),\n            )\n        else:\n            con.execute(\n                """\n                UPDATE school_network_year_data\n                SET data_json=?,source_name=?,imported_at=?\n                WHERE id=?\n                """,\n                (payload, source_name, now, int(existing["id"])),\n            )\n\n        if con.execute("PRAGMA foreign_key_check").fetchall():\n            raise RuntimeError("Foreign key check không đạt.")\n\n        row = con.execute(\n            """\n            SELECT data_json\n            FROM school_network_year_data\n            WHERE school_id=? AND school_year_id=? AND UPPER(TRIM(level_code))=?\n            ORDER BY id DESC\n            LIMIT 1\n            """,\n            (school_id, CURRENT_YEAR_ID, level),\n        ).fetchone()\n        if row is None or json.loads(row["data_json"] or "{}") != new_data:\n            raise RuntimeError("Post-check dữ liệu mạng lưới không khớp.")\n\n        con.commit()\n    except Exception:\n        con.rollback()\n        raise\n    finally:\n        con.close()\n\n    return RedirectResponse(\n        url=f"/mang-luoi-hien-hanh?school_id={school_id}&level={level}&status=saved",\n        status_code=303,\n    )\n'
TEMPLATE_STANDALONE = '<!DOCTYPE html>\n<html lang="vi">\n<head>\n    <meta charset="UTF-8">\n    <meta name="viewport" content="width=device-width, initial-scale=1.0">\n    <title>Mạng lưới năm học hiện hành</title>\n    <style>\n        body{font-family:Arial,sans-serif;margin:0;background:#f5f7fb;color:#1f2937}\n        .wrap{max-width:1320px;margin:0 auto;padding:18px}\n        .top{display:flex;justify-content:space-between;gap:16px;align-items:center;margin-bottom:14px}\n        .top h1{font-size:24px;margin:0}\n        .card{background:#fff;border:1px solid #dbe2ea;border-radius:10px;padding:16px;margin-bottom:14px}\n        .grid{display:grid;grid-template-columns:repeat(4,minmax(180px,1fr));gap:12px}\n        label{display:block;font-weight:700;font-size:13px;margin-bottom:5px}\n        select,input{width:100%;box-sizing:border-box;padding:9px 10px;border:1px solid #b8c2cc;border-radius:6px}\n        button,.btn{display:inline-block;padding:9px 14px;border:0;border-radius:6px;background:#0f766e;color:#fff;text-decoration:none;cursor:pointer}\n        .btn.secondary{background:#475569}\n        .notice{padding:10px 12px;border-radius:6px;margin-bottom:12px}\n        .ok{background:#dcfce7}.warn{background:#fff7ed}.info{background:#e0f2fe}\n        table{width:100%;border-collapse:collapse;font-size:13px}\n        th,td{border:1px solid #dbe2ea;padding:7px;vertical-align:top}\n        th{background:#eef2f7}\n        .ref{font-size:12px;margin:2px 0;color:#475569}\n        .missing{font-weight:700;color:#b45309}\n        .saved{font-weight:700;color:#047857}\n        .foot{display:flex;justify-content:flex-end;gap:10px;margin-top:12px}\n        @media(max-width:900px){.grid{grid-template-columns:1fr 1fr}}\n        @media(max-width:600px){.grid{grid-template-columns:1fr}.wrap{padding:10px}.top{display:block}}\n    </style>\n</head>\n<body>\n<div class="wrap">\n    <div class="top">\n        <div>\n            <h1>MẠNG LƯỚI NĂM HỌC HIỆN HÀNH</h1>\n            <div>Năm học <strong>{{ year_label }}</strong> · tham chiếu {{ base_year_label }}</div>\n        </div>\n        <div><a class="btn secondary" href="/">Trang chủ</a></div>\n    </div>\n\n    {% if status == "saved" %}\n    <div class="notice ok">✓ Đã lưu dữ liệu mạng lưới hiện hành.</div>\n    {% elif status == "stale" %}\n    <div class="notice warn">Dữ liệu tham chiếu đã thay đổi. Hãy tải lại trang rồi lưu lại.</div>\n    {% elif status %}\n    <div class="notice warn">Trạng thái: {{ status }}</div>\n    {% endif %}\n\n    <div class="card">\n        <div class="notice info">\n            Còn <strong>{{ missing_count }}</strong> trường đích trong phạm vi tài khoản đang thiếu ít nhất một dòng mạng lưới năm {{ year_label }}.\n            Ba nguồn tách điểm manual không xuất hiện ở màn hình này.\n        </div>\n\n        <form method="get" action="/mang-luoi-hien-hanh">\n            <div class="grid">\n                {% if actor.scope == "PROVINCE" %}\n                <div>\n                    <label>Xã/phường</label>\n                    <select name="commune_id" onchange="this.form.submit()">\n                        <option value="">-- Tất cả --</option>\n                        {% for c in communes %}\n                        <option value="{{ c.id }}" {% if selected_commune_id == c.id %}selected{% endif %}>{{ c.name }}</option>\n                        {% endfor %}\n                    </select>\n                </div>\n                {% endif %}\n\n                <div>\n                    <label>Tìm nhanh trường</label>\n                    <input id="schoolSearch" type="text" placeholder="Gõ từ đầu tên trường...">\n                </div>\n\n                <div>\n                    <label>Trường</label>\n                    <select id="schoolSelect" name="school_id">\n                        <option value="">-- Chọn trường --</option>\n                        {% for s in schools %}\n                        <option value="{{ s.id }}" data-name="{{ s.name|lower }}" {% if selected_school_id == s.id %}selected{% endif %}>\n                            {{ s.name }}{% if s.id in missing_target_ids %} — CHƯA CÓ {{ year_label }}{% endif %}\n                        </option>\n                        {% endfor %}\n                    </select>\n                </div>\n\n                <div>\n                    <label>Cấp học</label>\n                    <select name="level">\n                        <option value="">-- Chọn cấp --</option>\n                        {% for lv in levels %}\n                        <option value="{{ lv }}" {% if selected_level == lv %}selected{% endif %}>{{ level_labels.get(lv,lv) }}</option>\n                        {% endfor %}\n                    </select>\n                </div>\n            </div>\n\n            <div class="foot"><button type="submit">HIỂN THỊ</button></div>\n        </form>\n    </div>\n\n    {% if selected_school and selected_level %}\n    <form method="post" action="/mang-luoi-hien-hanh/luu">\n        <input type="hidden" name="school_id" value="{{ selected_school.id }}">\n        <input type="hidden" name="level" value="{{ selected_level }}">\n        <input type="hidden" name="state_hash" value="{{ state_hash }}">\n\n        <div class="card">\n            <div style="margin-bottom:10px">\n                <strong>{{ selected_school.name }}</strong> · {{ level_labels.get(selected_level,selected_level) }}\n                {% if current %}\n                <span class="saved">— Đã có dữ liệu {{ year_label }}, có thể cập nhật lại.</span>\n                {% else %}\n                <span class="missing">— Chưa có dữ liệu {{ year_label }}.</span>\n                {% endif %}\n            </div>\n\n            <table>\n                <thead>\n                    <tr>\n                        <th style="width:24%">Chỉ tiêu</th>\n                        <th style="width:30%">Tham chiếu {{ base_year_label }}</th>\n                        <th>Số liệu hiện hành {{ year_label }}</th>\n                    </tr>\n                </thead>\n                <tbody>\n                {% for f in fields %}\n                    <tr>\n                        <td>\n                            <strong>{{ f.label }}</strong>\n                            <div style="font-size:11px;color:#64748b">{{ f.key }}</div>\n                        </td>\n                        <td>\n                            {% for r in f.references %}\n                            <div class="ref">{{ r.school_name }}: <strong>{{ r.value if r.value is not none else "NULL" }}</strong></div>\n                            {% endfor %}\n                        </td>\n                        <td>\n                            <input type="text" name="field__{{ f.key }}" value="{{ f.current_value }}" placeholder="Nhập số liệu thực tế; để trống = NULL">\n                        </td>\n                    </tr>\n                {% endfor %}\n                </tbody>\n            </table>\n\n            <div class="notice warn" style="margin-top:12px">\n                Không tự cộng số liệu trường cũ. Không coi NULL là 0.\n                Hãy nhập số liệu thực tế của trường sau sáp nhập. Với “đạt chuẩn quốc gia”, dùng 1 = Có, 0 = Không, để trống = Chưa xác định.\n            </div>\n\n            <div class="foot"><button type="submit">LƯU MẠNG LƯỚI {{ year_label }}</button></div>\n        </div>\n    </form>\n    {% endif %}\n</div>\n\n<script>\n(function(){\n    const q = document.getElementById(\'schoolSearch\');\n    const sel = document.getElementById(\'schoolSelect\');\n    if(!q || !sel) return;\n    const original = Array.from(sel.options).map(o => ({\n        value:o.value, text:o.text, name:(o.dataset.name||o.text).toLowerCase()\n    }));\n    q.addEventListener(\'input\', function(){\n        const term = q.value.trim().toLowerCase();\n        const current = sel.value;\n        sel.innerHTML = \'\';\n        original.forEach((o, idx) => {\n            if(idx === 0 || !term || o.name.startsWith(term) || o.name.includes(term)){\n                const n = document.createElement(\'option\');\n                n.value = o.value;\n                n.text = o.text;\n                if(o.value === current) n.selected = true;\n                sel.appendChild(n);\n            }\n        });\n    });\n})();\n</script>\n</body>\n</html>\n'


def log_write(f, *parts):
    s = " ".join(str(x) for x in parts)
    print(s)
    f.write(s + "\n")
    f.flush()


def sha256_file(path: Path):
    h = hashlib.sha256()
    with path.open("rb") as src:
        for b in iter(lambda: src.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def backup_file(path: Path, backup_root: Path):
    if not path.exists():
        return None
    rel = path.relative_to(ROOT)
    dst = backup_root / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dst)
    return dst


def restore_file(src_backup: Path | None, target: Path):
    if src_backup and src_backup.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_backup, target)
    elif target.exists():
        target.unlink()


def main():
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ROUTERS.mkdir(parents=True, exist_ok=True)
    TEMPLATES.mkdir(parents=True, exist_ok=True)

    with OUT.open("w", encoding="utf-8-sig", newline="\n") as f:
        log_write(f, "=" * 150)
        log_write(f, "BATCH 18 - CÀI ĐẶT MÀN HÌNH MẠNG LƯỚI NĂM HỌC HIỆN HÀNH")
        log_write(f, "KHÔNG GHI DỮ LIỆU NGHIỆP VỤ TRONG LÚC CÀI; CHỈ THÊM ROUTER + TEMPLATE + ĐĂNG KÝ ROUTER")
        log_write(f, "=" * 150)

        db_sha = sha256_file(DB)
        log_write(f, "DB_SHA =", db_sha)
        log_write(f, "EXPECTED_DB_SHA =", EXPECTED_DB_SHA)
        if db_sha != EXPECTED_DB_SHA:
            raise RuntimeError("DB SHA khác nền Batch 17.")

        con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True, timeout=30)
        try:
            integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
            fk = con.execute("PRAGMA foreign_key_check").fetchall()
        finally:
            con.close()

        log_write(f, "INTEGRITY =", integrity)
        log_write(f, "FK =", len(fk))
        if integrity != "ok" or fk:
            raise RuntimeError("Database health không đạt.")

        if not MAIN.exists():
            raise RuntimeError("Không tìm thấy app/main.py")

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_root = BACKUP_DIR / f"source_truoc_BATCH18_{ts}"

        main_bak = backup_file(MAIN, backup_root)
        router_bak = backup_file(ROUTER_FILE, backup_root)
        template_bak = backup_file(TEMPLATE_FILE, backup_root)

        log_write(f, "SOURCE_BACKUP_DIR =", backup_root)
        log_write(f, "MAIN_SHA_BEFORE =", sha256_file(MAIN))

        main_text = MAIN.read_text(encoding="utf-8", errors="strict")

        if MARKER_START in main_text or MARKER_END in main_text:
            log_write(f, "MAIN_PATCH = ALREADY_PRESENT")
        else:
            patch = (
                "\n\n"
                + MARKER_START + "\n"
                + "from app.routers import network_current as _network_current\n"
                + "app.include_router(_network_current.router)\n"
                + MARKER_END + "\n"
            )
            main_text = main_text.rstrip() + patch
            MAIN.write_text(main_text, encoding="utf-8")
            log_write(f, "MAIN_PATCH = ADDED")

        ROUTER_FILE.write_text(ROUTER_CODE, encoding="utf-8")
        TEMPLATE_FILE.write_text(TEMPLATE_STANDALONE, encoding="utf-8")

        try:
            py_compile.compile(str(ROUTER_FILE), doraise=True)
            py_compile.compile(str(MAIN), doraise=True)
            log_write(f, "PY_COMPILE = PASS")
        except Exception:
            restore_file(main_bak, MAIN)
            restore_file(router_bak, ROUTER_FILE)
            restore_file(template_bak, TEMPLATE_FILE)
            log_write(f, "ROLLBACK_SOURCE = PASS")
            raise

        router_text = ROUTER_FILE.read_text(encoding="utf-8")
        required = [
            'CURRENT_YEAR_ID = 2',
            'MANUAL_SPLIT_SOURCE_IDS = {1510, 1522, 1658}',
            '@router.get("")',
            '@router.post("/luu")',
            '_backup_db()',
            'BEGIN IMMEDIATE',
            'PRAGMA foreign_key_check',
        ]
        missing = [x for x in required if x not in router_text]
        if missing:
            restore_file(main_bak, MAIN)
            restore_file(router_bak, ROUTER_FILE)
            restore_file(template_bak, TEMPLATE_FILE)
            log_write(f, "ROLLBACK_SOURCE = PASS")
            raise RuntimeError(f"Router thiếu gate bắt buộc: {missing}")

        log_write(f, "ROUTER_FILE =", ROUTER_FILE)
        log_write(f, "ROUTER_SHA =", sha256_file(ROUTER_FILE))
        log_write(f, "TEMPLATE_FILE =", TEMPLATE_FILE)
        log_write(f, "TEMPLATE_SHA =", sha256_file(TEMPLATE_FILE))
        log_write(f, "MAIN_SHA_AFTER =", sha256_file(MAIN))
        log_write(f, "DB_SHA_AFTER_INSTALL =", sha256_file(DB))
        log_write(f, "DATABASE_WRITES_THIS_RUN = 0")
        log_write(f, "INSTALL_BATCH18_SUCCESS = YES")
        log_write(f, "TEST_URL = http://127.0.0.1:8000/mang-luoi-hien-hanh")
        log_write(f, "NEXT = Khởi động lại Uvicorn, mở TEST_URL; chọn trường/cấp học và kiểm tra màn hình tham chiếu trước khi nhập dữ liệu thật.")
        log_write(f, "=" * 150)

    return 0


if __name__ == "__main__":
    try:
        rc = main()
    except Exception as exc:
        try:
            EXPORT_DIR.mkdir(parents=True, exist_ok=True)
            with OUT.open("a", encoding="utf-8-sig", newline="\n") as f:
                log_write(f, "")
                log_write(f, "=" * 150)
                log_write(f, "INSTALL_BATCH18_SUCCESS = NO")
                log_write(f, "ERROR =", repr(exc))
                if DB.exists():
                    log_write(f, "DB_SHA_CURRENT =", sha256_file(DB))
                log_write(f, "DỪNG AN TOÀN.")
                log_write(f, "=" * 150)
        except Exception:
            print("ERROR =", repr(exc))
        rc = 1
    sys.exit(rc)
