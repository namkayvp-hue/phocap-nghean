# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import py_compile
import re
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
MAIN = ROOT / "app" / "main.py"
MENU = ROOT / "app" / "templates" / "partials" / "dropdown_menu_v1.html"
ROUTER = ROOT / "app" / "routers" / "survey_cleanup_safe.py"
TEMPLATE = ROOT / "app" / "templates" / "data_tools" / "survey_cleanup.html"

BACKUP_DIR = ROOT / "backups"
EXPORT_DIR = ROOT / "exports"
OUT = EXPORT_DIR / "BATCH_CAI_CHUC_NANG_XOA_DU_LIEU_DIEU_TRA_23.txt"

EXPECTED_DB_SHA = "2a43e36ff8f192abb46668faa1366ed7242984bfd876f90572cd83b90ee7837e"

ROUTER_CODE = '# -*- coding: utf-8 -*-\nfrom __future__ import annotations\n\nimport hashlib\nimport json\nimport sqlite3\nfrom collections import defaultdict\nfrom datetime import date, datetime\nfrom pathlib import Path\nfrom typing import Any\n\nfrom fastapi import APIRouter, Form, Request\nfrom fastapi.responses import RedirectResponse\nfrom fastapi.templating import Jinja2Templates\n\n\nROOT = Path(__file__).resolve().parents[2]\nDB_PATH = ROOT / "data" / "phocap.db"\nBACKUP_DIR = ROOT / "backups"\nEXPORT_DIR = ROOT / "exports"\nTEMPLATE_DIR = ROOT / "app" / "templates"\n\nPATH = "/cong-cu-du-lieu/don-dep-dieu-tra"\n\nrouter = APIRouter(tags=["Công cụ dữ liệu"])\ntemplates = Jinja2Templates(directory=str(TEMPLATE_DIR))\n\n# Chỉ xóa cây dữ liệu bắt đầu từ HỘ DÂN.\n# Tuyệt đối không dùng các bảng nền dưới đây làm mục tiêu DELETE.\nPROTECTED_EXACT = {\n    "schools",\n    "school_years",\n    "communes",\n    "classes",\n    "users",\n    "roles",\n    "staff_members",\n    "staff_year_records",\n    "student_enrollments",\n    "student_reconciliation_source_states",\n    "student_reconciliation_state_enrollments",\n    "student_reconciliation_import_logs",\n    "survey_batches",\n    "survey_school_assignments",\n    "survey_commune_execution_states",\n    "survey_execution_workflow_logs",\n    "survey_investigation_teams",\n    "survey_investigation_team_members",\n    "survey_investigation_participants",\n    "survey_participant_submissions",\n    "survey_team_area_assignments",\n    "survey_team_generation_logs",\n    "survey_team_registration_logs",\n}\n\nPROTECTED_PREFIXES = (\n    "school_",\n    "staff_",\n    "student_",\n    "class_",\n    "merger_",\n)\n\n# Các bảng này có thể là ánh xạ trực tiếp tới một phiếu/hộ cụ thể.\n# Nếu DB có FK thật sự tới household/person/form thì được phép xóa theo cây.\nALLOWED_SURVEY_PREFIXES = (\n    "household",\n    "survey_people",\n    "survey_person_",\n    "survey_form",\n    "survey_household",\n)\n\n\ndef _conn() -> sqlite3.Connection:\n    con = sqlite3.connect(str(DB_PATH), timeout=60)\n    con.row_factory = sqlite3.Row\n    con.execute("PRAGMA foreign_keys=ON")\n    return con\n\n\ndef _table_exists(con: sqlite3.Connection, table: str) -> bool:\n    return con.execute(\n        "SELECT 1 FROM sqlite_master WHERE type=\'table\' AND name=?",\n        (table,),\n    ).fetchone() is not None\n\n\ndef _cols(con: sqlite3.Connection, table: str) -> list[str]:\n    if not _table_exists(con, table):\n        return []\n    return [\n        str(r[1])\n        for r in con.execute(f\'PRAGMA table_info("{table}")\').fetchall()\n    ]\n\n\ndef _pk_col(con: sqlite3.Connection, table: str) -> str | None:\n    if not _table_exists(con, table):\n        return None\n    rows = con.execute(f\'PRAGMA table_info("{table}")\').fetchall()\n    pks = [r for r in rows if int(r[5] or 0) > 0]\n    if len(pks) == 1:\n        return str(pks[0][1])\n    if "id" in [str(r[1]) for r in rows]:\n        return "id"\n    return None\n\n\ndef _actor(request: Request) -> dict[str, Any] | None:\n    uid = request.session.get("user_id")\n    if not uid:\n        return None\n\n    with _conn() as con:\n        if not _table_exists(con, "users"):\n            return None\n\n        user = con.execute("SELECT * FROM users WHERE id=?", (int(uid),)).fetchone()\n        if user is None:\n            return None\n        user = dict(user)\n\n        if "is_active" in user and not bool(user.get("is_active")):\n            return None\n\n        role_code = ""\n        if user.get("role_code"):\n            role_code = str(user.get("role_code") or "")\n        elif user.get("role_id") is not None and _table_exists(con, "roles"):\n            rcols = _cols(con, "roles")\n            role = con.execute(\n                "SELECT * FROM roles WHERE id=?",\n                (int(user["role_id"]),),\n            ).fetchone()\n            if role:\n                rd = dict(role)\n                for key in ("code", "role_code", "name"):\n                    if key in rcols and rd.get(key):\n                        role_code = str(rd[key])\n                        break\n\n        username = str(user.get("username") or "").strip().lower()\n        role_norm = role_code.strip().upper()\n\n        allowed = (\n            username.startswith("admin.")\n            or any(x in role_norm for x in ("ADMIN", "SOGDDT", "PROVINCE", "SO"))\n        )\n\n        return {\n            "id": int(user["id"]),\n            "username": username,\n            "full_name": str(user.get("full_name") or user.get("name") or username),\n            "role_code": role_code,\n            "allowed": bool(allowed),\n        }\n\n\ndef _require_admin(request: Request) -> dict[str, Any] | None:\n    actor = _actor(request)\n    if actor is None or not actor["allowed"]:\n        return None\n    return actor\n\n\ndef _household_date_column(con: sqlite3.Connection) -> str:\n    cols = _cols(con, "households")\n    for name in ("created_at", "created_on", "inserted_at"):\n        if name in cols:\n            return name\n    raise RuntimeError(\n        "Bảng households không có cột created_at/created_on/inserted_at. "\n        "Dừng để không đoán sai ngày nhập dữ liệu."\n    )\n\n\ndef _parse_date(value: str, label: str) -> date:\n    text = str(value or "").strip()\n    try:\n        return datetime.strptime(text, "%Y-%m-%d").date()\n    except Exception:\n        raise ValueError(f"{label} không hợp lệ.")\n\n\ndef _validate_range(from_date: str, to_date: str) -> tuple[date, date]:\n    d1 = _parse_date(from_date, "Từ ngày")\n    d2 = _parse_date(to_date, "Đến ngày")\n    if d1 > d2:\n        raise ValueError("Từ ngày không được lớn hơn Đến ngày.")\n    return d1, d2\n\n\ndef _selected_households(\n    con: sqlite3.Connection,\n    from_date: str,\n    to_date: str,\n) -> list[dict[str, Any]]:\n    date_col = _household_date_column(con)\n    hcols = _cols(con, "households")\n    wanted = [\n        c for c in ("id", "code", "head_name", "commune_id", date_col)\n        if c in hcols\n    ]\n\n    cur = con.execute(\n        "SELECT "\n        + ",".join(f\'"{c}"\' for c in wanted)\n        + f\' FROM "households" \'\n          f\'WHERE date("{date_col}") BETWEEN date(?) AND date(?) \'\n          f\'ORDER BY "{date_col}", id\',\n        (from_date, to_date),\n    )\n    names = [d[0] for d in cur.description]\n    return [dict(zip(names, row)) for row in cur.fetchall()]\n\n\ndef _all_tables(con: sqlite3.Connection) -> list[str]:\n    return [\n        str(r[0])\n        for r in con.execute(\n            """\n            SELECT name\n            FROM sqlite_master\n            WHERE type=\'table\' AND name NOT LIKE \'sqlite_%\'\n            ORDER BY name\n            """\n        ).fetchall()\n    ]\n\n\ndef _is_protected(table: str) -> bool:\n    low = table.lower()\n    if low in PROTECTED_EXACT:\n        return True\n    if any(low.startswith(prefix) for prefix in PROTECTED_PREFIXES):\n        return True\n    return False\n\n\ndef _allowed_child_table(table: str) -> bool:\n    low = table.lower()\n    if _is_protected(low):\n        return False\n    return any(low.startswith(prefix) for prefix in ALLOWED_SURVEY_PREFIXES)\n\n\ndef _fk_children(con: sqlite3.Connection) -> dict[str, list[dict[str, str]]]:\n    result: dict[str, list[dict[str, str]]] = defaultdict(list)\n\n    for child in _all_tables(con):\n        if _is_protected(child):\n            # Vẫn đọc FK để có thể phát hiện bảng bảo vệ đang chặn xóa.\n            pass\n\n        try:\n            fks = con.execute(\n                f\'PRAGMA foreign_key_list("{child}")\'\n            ).fetchall()\n        except sqlite3.Error:\n            continue\n\n        for fk in fks:\n            parent = str(fk[2])\n            result[parent].append({\n                "child_table": child,\n                "child_col": str(fk[3]),\n                "parent_col": str(fk[4] or "id"),\n            })\n\n    return result\n\n\ndef _ids_for_fk(\n    con: sqlite3.Connection,\n    table: str,\n    pk_col: str,\n    fk_col: str,\n    parent_ids: list[Any],\n) -> list[Any]:\n    if not parent_ids:\n        return []\n\n    placeholders = ",".join("?" for _ in parent_ids)\n    rows = con.execute(\n        f\'SELECT "{pk_col}" FROM "{table}" \'\n        f\'WHERE "{fk_col}" IN ({placeholders})\',\n        tuple(parent_ids),\n    ).fetchall()\n\n    return [r[0] for r in rows]\n\n\ndef _count_for_fk(\n    con: sqlite3.Connection,\n    table: str,\n    fk_col: str,\n    parent_ids: list[Any],\n) -> int:\n    if not parent_ids:\n        return 0\n\n    placeholders = ",".join("?" for _ in parent_ids)\n    return int(con.execute(\n        f\'SELECT COUNT(*) FROM "{table}" \'\n        f\'WHERE "{fk_col}" IN ({placeholders})\',\n        tuple(parent_ids),\n    ).fetchone()[0])\n\n\ndef _build_delete_plan(\n    con: sqlite3.Connection,\n    household_ids: list[int],\n) -> dict[str, Any]:\n    relations = _fk_children(con)\n\n    delete_counts: dict[str, int] = defaultdict(int)\n    delete_specs: list[dict[str, Any]] = []\n    blockers: list[dict[str, Any]] = []\n    visited: set[tuple[str, str, tuple[Any, ...]]] = set()\n\n    def walk(parent_table: str, parent_ids: list[Any], depth: int):\n        if not parent_ids:\n            return\n\n        for rel in relations.get(parent_table, []):\n            child = rel["child_table"]\n            child_col = rel["child_col"]\n            parent_col = rel["parent_col"]\n\n            # Chỉ xử lý FK trỏ vào PK/id của parent.\n            parent_pk = _pk_col(con, parent_table)\n            if not parent_pk or parent_col != parent_pk:\n                continue\n\n            count = _count_for_fk(\n                con, child, child_col, parent_ids\n            )\n            if count <= 0:\n                continue\n\n            if _is_protected(child):\n                blockers.append({\n                    "table": child,\n                    "count": count,\n                    "reason": (\n                        "Bảng được bảo vệ theo yêu cầu: không xóa trường/lớp/"\n                        "giáo viên/học sinh đối chiếu hoặc cấu hình điều tra."\n                    ),\n                })\n                continue\n\n            if not _allowed_child_table(child):\n                blockers.append({\n                    "table": child,\n                    "count": count,\n                    "reason": (\n                        "Có dữ liệu phụ thuộc nhưng bảng không nằm trong nhóm "\n                        "dữ liệu hộ dân được phép xóa tự động."\n                    ),\n                })\n                continue\n\n            child_pk = _pk_col(con, child)\n            child_ids = []\n            if child_pk:\n                child_ids = _ids_for_fk(\n                    con, child, child_pk, child_col, parent_ids\n                )\n\n            # Đi sâu trước để xóa con trước cha.\n            if child_pk and child_ids:\n                key = (\n                    child,\n                    child_pk,\n                    tuple(sorted(set(child_ids), key=lambda x: str(x))),\n                )\n                if key not in visited:\n                    visited.add(key)\n                    walk(child, list(key[2]), depth + 1)\n\n            delete_specs.append({\n                "table": child,\n                "fk_col": child_col,\n                "parent_ids": list(parent_ids),\n                "count": count,\n                "depth": depth + 1,\n            })\n            delete_counts[child] += count\n\n    walk("households", household_ids, 0)\n\n    delete_counts["households"] = len(household_ids)\n\n    return {\n        "delete_counts": dict(sorted(delete_counts.items())),\n        "delete_specs": delete_specs,\n        "blockers": blockers,\n    }\n\n\ndef _direct_logical_counts(\n    con: sqlite3.Connection,\n    household_ids: list[int],\n) -> dict[str, int]:\n    """\n    Thống kê bổ sung để người dùng dễ kiểm tra.\n    Không dùng các bảng này để đoán DELETE nếu không có FK thật.\n    """\n    result: dict[str, int] = {}\n    if not household_ids:\n        return result\n\n    placeholders = ",".join("?" for _ in household_ids)\n\n    for table in ("survey_people", "survey_forms"):\n        if not _table_exists(con, table):\n            continue\n        if "household_id" not in _cols(con, table):\n            continue\n        result[table] = int(con.execute(\n            f\'SELECT COUNT(*) FROM "{table}" \'\n            f\'WHERE household_id IN ({placeholders})\',\n            tuple(household_ids),\n        ).fetchone()[0])\n\n    return result\n\n\ndef _preview(\n    con: sqlite3.Connection,\n    from_date: str,\n    to_date: str,\n) -> dict[str, Any]:\n    _validate_range(from_date, to_date)\n    households = _selected_households(con, from_date, to_date)\n    household_ids = [int(x["id"]) for x in households]\n    plan = _build_delete_plan(con, household_ids)\n\n    return {\n        "from_date": from_date,\n        "to_date": to_date,\n        "household_date_column": _household_date_column(con),\n        "household_count": len(households),\n        "households_sample": households[:20],\n        "direct_counts": _direct_logical_counts(con, household_ids),\n        "delete_counts": plan["delete_counts"],\n        "blockers": plan["blockers"],\n        "_household_ids": household_ids,\n        "_delete_specs": plan["delete_specs"],\n    }\n\n\ndef _backup_db() -> Path:\n    BACKUP_DIR.mkdir(parents=True, exist_ok=True)\n    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")\n    path = BACKUP_DIR / f"backup_truoc_xoa_du_lieu_dieu_tra_{ts}.db"\n\n    src = sqlite3.connect(str(DB_PATH), timeout=60)\n    dst = sqlite3.connect(str(path), timeout=60)\n    try:\n        src.backup(dst)\n    finally:\n        dst.close()\n        src.close()\n\n    chk = sqlite3.connect(\n        f"file:{path.as_posix()}?mode=ro",\n        uri=True,\n        timeout=30,\n    )\n    try:\n        integrity = chk.execute("PRAGMA integrity_check").fetchone()[0]\n        fk = chk.execute("PRAGMA foreign_key_check").fetchall()\n    finally:\n        chk.close()\n\n    if integrity != "ok" or fk:\n        raise RuntimeError(\n            f"Backup không đạt: integrity={integrity}, fk={len(fk)}"\n        )\n\n    return path\n\n\ndef _db_sha() -> str:\n    h = hashlib.sha256()\n    with DB_PATH.open("rb") as f:\n        for block in iter(lambda: f.read(1024 * 1024), b""):\n            h.update(block)\n    return h.hexdigest()\n\n\ndef _delete_by_spec(\n    con: sqlite3.Connection,\n    spec: dict[str, Any],\n) -> int:\n    parent_ids = spec["parent_ids"]\n    if not parent_ids:\n        return 0\n\n    placeholders = ",".join("?" for _ in parent_ids)\n    cur = con.execute(\n        f\'DELETE FROM "{spec["table"]}" \'\n        f\'WHERE "{spec["fk_col"]}" IN ({placeholders})\',\n        tuple(parent_ids),\n    )\n    return int(cur.rowcount or 0)\n\n\ndef _write_audit_file(payload: dict[str, Any]) -> Path:\n    EXPORT_DIR.mkdir(parents=True, exist_ok=True)\n    folder = EXPORT_DIR / "dieu_tra_cleanup_logs"\n    folder.mkdir(parents=True, exist_ok=True)\n    ts = datetime.now().strftime("%Y%m%d_%H%M%S")\n    path = folder / f"xoa_du_lieu_dieu_tra_{ts}.json"\n    path.write_text(\n        json.dumps(payload, ensure_ascii=False, indent=2, default=str),\n        encoding="utf-8-sig",\n    )\n    return path\n\n\n@router.get(PATH)\ndef cleanup_page(\n    request: Request,\n    status: str | None = None,\n):\n    actor = _require_admin(request)\n    if actor is None:\n        return RedirectResponse(url="/", status_code=303)\n\n    return templates.TemplateResponse(\n        request=request,\n        name="data_tools/survey_cleanup.html",\n        context={\n            "actor": actor,\n            "status": status,\n            "preview": None,\n            "from_date": "",\n            "to_date": "",\n        },\n    )\n\n\n@router.post(PATH + "/xem-truoc")\ndef cleanup_preview(\n    request: Request,\n    from_date: str = Form(...),\n    to_date: str = Form(...),\n):\n    actor = _require_admin(request)\n    if actor is None:\n        return RedirectResponse(url="/", status_code=303)\n\n    preview = None\n    error = None\n\n    try:\n        with _conn() as con:\n            con.execute("PRAGMA query_only=ON")\n            preview = _preview(con, from_date, to_date)\n    except Exception as exc:\n        error = str(exc)\n\n    return templates.TemplateResponse(\n        request=request,\n        name="data_tools/survey_cleanup.html",\n        context={\n            "actor": actor,\n            "status": "preview",\n            "preview": preview,\n            "error": error,\n            "from_date": from_date,\n            "to_date": to_date,\n        },\n    )\n\n\n@router.post(PATH + "/xoa")\ndef cleanup_execute(\n    request: Request,\n    from_date: str = Form(...),\n    to_date: str = Form(...),\n    confirm_text: str = Form(...),\n):\n    actor = _require_admin(request)\n    if actor is None:\n        return RedirectResponse(url="/", status_code=303)\n\n    if str(confirm_text or "").strip().upper() != "XOA DU LIEU DIEU TRA":\n        return templates.TemplateResponse(\n            request=request,\n            name="data_tools/survey_cleanup.html",\n            context={\n                "actor": actor,\n                "status": "confirm_error",\n                "preview": None,\n                "error": (\n                    "Phải nhập đúng: XOA DU LIEU DIEU TRA"\n                ),\n                "from_date": from_date,\n                "to_date": to_date,\n            },\n        )\n\n    _validate_range(from_date, to_date)\n\n    # Lập lại preview ngay trước ghi để tránh dùng dữ liệu cũ.\n    with _conn() as con:\n        preview = _preview(con, from_date, to_date)\n\n    if preview["household_count"] <= 0:\n        return templates.TemplateResponse(\n            request=request,\n            name="data_tools/survey_cleanup.html",\n            context={\n                "actor": actor,\n                "status": "no_data",\n                "preview": preview,\n                "error": "Không có hộ dân nào trong khoảng ngày đã chọn.",\n                "from_date": from_date,\n                "to_date": to_date,\n            },\n        )\n\n    if preview["blockers"]:\n        return templates.TemplateResponse(\n            request=request,\n            name="data_tools/survey_cleanup.html",\n            context={\n                "actor": actor,\n                "status": "blocked",\n                "preview": preview,\n                "error": (\n                    "Dừng an toàn vì phát hiện dữ liệu phụ thuộc nằm ngoài "\n                    "nhóm dữ liệu hộ dân được phép xóa."\n                ),\n                "from_date": from_date,\n                "to_date": to_date,\n            },\n        )\n\n    backup = _backup_db()\n    sha_before = _db_sha()\n\n    con = _conn()\n    deleted: dict[str, int] = defaultdict(int)\n\n    try:\n        con.execute("BEGIN IMMEDIATE")\n\n        # Kiểm tra sức khỏe ngay trong transaction.\n        if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok":\n            raise RuntimeError("integrity_check trước xóa không đạt.")\n        if con.execute("PRAGMA foreign_key_check").fetchall():\n            raise RuntimeError("foreign_key_check trước xóa không đạt.")\n\n        # Xóa bảng con theo thứ tự đã thu thập (đệ quy thêm trước cha).\n        # Có thể có spec trùng đường FK; SQLite DELETE lần sau sẽ = 0.\n        for spec in preview["_delete_specs"]:\n            n = _delete_by_spec(con, spec)\n            deleted[spec["table"]] += n\n\n        household_ids = preview["_household_ids"]\n        placeholders = ",".join("?" for _ in household_ids)\n        cur = con.execute(\n            f\'DELETE FROM "households" WHERE id IN ({placeholders})\',\n            tuple(household_ids),\n        )\n        deleted["households"] += int(cur.rowcount or 0)\n\n        if con.execute("PRAGMA foreign_key_check").fetchall():\n            raise RuntimeError(\n                "foreign_key_check sau xóa không đạt; tự rollback."\n            )\n\n        con.commit()\n\n    except Exception:\n        con.rollback()\n        raise\n    finally:\n        con.close()\n\n    # Kiểm tra DB sau commit.\n    check = _conn()\n    try:\n        integrity_after = check.execute(\n            "PRAGMA integrity_check"\n        ).fetchone()[0]\n        fk_after = check.execute(\n            "PRAGMA foreign_key_check"\n        ).fetchall()\n    finally:\n        check.close()\n\n    if integrity_after != "ok" or fk_after:\n        raise RuntimeError(\n            "DB sau commit không đạt kiểm tra. "\n            "Dùng backup vừa tạo để khôi phục."\n        )\n\n    sha_after = _db_sha()\n\n    audit_payload = {\n        "action": "XOA_DU_LIEU_HO_DAN_THEO_KHOANG_NGAY",\n        "executed_at": datetime.now().isoformat(timespec="seconds"),\n        "actor_user_id": actor["id"],\n        "actor_username": actor["username"],\n        "from_date": from_date,\n        "to_date": to_date,\n        "date_column": preview["household_date_column"],\n        "planned_counts": preview["delete_counts"],\n        "deleted_counts": dict(sorted(deleted.items())),\n        "protected_data_policy": (\n            "Không xóa trường, lớp, giáo viên, tài khoản, học sinh đối chiếu, "\n            "đợt điều tra, phân công trường/tổ điều tra."\n        ),\n        "backup_path": str(backup),\n        "db_sha_before": sha_before,\n        "db_sha_after": sha_after,\n        "integrity_after": integrity_after,\n        "fk_after": len(fk_after),\n    }\n\n    audit_file = _write_audit_file(audit_payload)\n\n    return templates.TemplateResponse(\n        request=request,\n        name="data_tools/survey_cleanup.html",\n        context={\n            "actor": actor,\n            "status": "deleted",\n            "preview": None,\n            "deleted": audit_payload,\n            "audit_file": str(audit_file),\n            "error": None,\n            "from_date": "",\n            "to_date": "",\n        },\n    )\n'
TEMPLATE_CODE = '<!DOCTYPE html>\n<html lang="vi">\n<head>\n    <meta charset="UTF-8">\n    <meta name="viewport" content="width=device-width, initial-scale=1.0">\n    <title>Dọn dẹp dữ liệu điều tra</title>\n    <style>\n        body{font-family:Arial,sans-serif;margin:0;background:#f4f7fb;color:#1f2937}\n        .wrap{max-width:1120px;margin:0 auto;padding:22px}\n        .top{display:flex;justify-content:space-between;align-items:center;gap:15px;margin-bottom:16px}\n        .top h1{margin:0;font-size:26px}\n        .card{background:#fff;border:1px solid #dbe3ee;border-radius:12px;padding:18px;margin-bottom:16px}\n        .grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}\n        label{display:block;font-weight:700;margin-bottom:6px}\n        input{width:100%;box-sizing:border-box;padding:10px;border:1px solid #b8c4d2;border-radius:7px}\n        button,.btn{border:0;border-radius:7px;padding:10px 15px;font-weight:700;cursor:pointer;text-decoration:none;display:inline-block}\n        .primary{background:#1769aa;color:#fff}.danger{background:#b42318;color:#fff}.secondary{background:#475569;color:#fff}\n        .notice{padding:12px;border-radius:8px;margin-bottom:14px;line-height:1.5}\n        .info{background:#e8f3ff}.warn{background:#fff4e5}.error{background:#feecec}.ok{background:#e8f7ec}\n        table{width:100%;border-collapse:collapse;font-size:14px}\n        th,td{border:1px solid #dbe3ee;padding:8px;vertical-align:top}\n        th{background:#edf3f8;text-align:left}\n        .actions{display:flex;justify-content:flex-end;gap:10px;margin-top:14px;flex-wrap:wrap}\n        .danger-box{border:2px solid #dc2626;background:#fff7f7}\n        code{background:#eef2f7;padding:2px 5px;border-radius:4px}\n        @media(max-width:700px){.grid{grid-template-columns:1fr}.wrap{padding:12px}.top{display:block}}\n    </style>\n</head>\n<body>\n<div class="wrap">\n    <div class="top">\n        <div>\n            <h1>DỌN DẸP DỮ LIỆU ĐIỀU TRA</h1>\n            <div>Chỉ dành cho quản trị cấp Sở</div>\n        </div>\n        <a href="/" class="btn secondary">Trang chủ</a>\n    </div>\n\n    <div class="notice info">\n        <strong>Phạm vi xóa:</strong> chỉ các hộ dân được đưa vào hệ thống trong khoảng\n        <strong>Từ ngày – Đến ngày</strong> và dữ liệu con gắn trực tiếp với các hộ đó\n        (thành viên, dữ liệu năm của đối tượng, phiếu điều tra và ánh xạ phụ thuộc có FK).\n        <br>\n        <strong>Không xóa:</strong> trường, lớp, CBQL/GV/NV, tài khoản, dữ liệu học sinh đối chiếu,\n        năm học, xã/phường, đợt điều tra, phân công trường và tổ điều tra.\n    </div>\n\n    {% if error %}\n    <div class="notice error"><strong>Dừng an toàn:</strong> {{ error }}</div>\n    {% endif %}\n\n    {% if status == "deleted" and deleted %}\n    <div class="notice ok">\n        <strong>Đã xóa thành công.</strong><br>\n        Backup trước xóa: <code>{{ deleted.backup_path }}</code><br>\n        Log kiểm toán: <code>{{ audit_file }}</code>\n    </div>\n\n    <div class="card">\n        <h3>Kết quả xóa</h3>\n        <table>\n            <thead><tr><th>Bảng dữ liệu hộ dân</th><th>Số dòng đã xóa</th></tr></thead>\n            <tbody>\n            {% for table, count in deleted.deleted_counts.items() %}\n                <tr><td>{{ table }}</td><td>{{ count }}</td></tr>\n            {% endfor %}\n            </tbody>\n        </table>\n    </div>\n    {% endif %}\n\n    <div class="card">\n        <form method="post" action="/cong-cu-du-lieu/don-dep-dieu-tra/xem-truoc">\n            <div class="grid">\n                <div>\n                    <label>Từ ngày</label>\n                    <input type="date" name="from_date" value="{{ from_date }}" required>\n                </div>\n                <div>\n                    <label>Đến ngày</label>\n                    <input type="date" name="to_date" value="{{ to_date }}" required>\n                </div>\n            </div>\n            <div class="actions">\n                <button class="btn primary" type="submit">XEM TRƯỚC DỮ LIỆU SẼ XÓA</button>\n            </div>\n        </form>\n    </div>\n\n    {% if preview %}\n    <div class="card">\n        <h3>Xem trước</h3>\n        <div class="notice warn">\n            Khoảng ngày: <strong>{{ preview.from_date }}</strong> đến\n            <strong>{{ preview.to_date }}</strong> ·\n            Cột ngày dùng để lọc: <code>{{ preview.household_date_column }}</code><br>\n            Số hộ phù hợp: <strong>{{ preview.household_count }}</strong>\n        </div>\n\n        <table>\n            <thead><tr><th>Bảng sẽ xóa</th><th>Số dòng dự kiến</th></tr></thead>\n            <tbody>\n            {% for table, count in preview.delete_counts.items() %}\n                <tr><td>{{ table }}</td><td>{{ count }}</td></tr>\n            {% endfor %}\n            </tbody>\n        </table>\n\n        {% if preview.blockers %}\n        <div class="notice error" style="margin-top:14px">\n            <strong>Không cho phép xóa.</strong> Có dữ liệu phụ thuộc nằm ngoài phạm vi được phép:\n            <ul>\n            {% for b in preview.blockers %}\n                <li><code>{{ b.table }}</code>: {{ b.count }} dòng — {{ b.reason }}</li>\n            {% endfor %}\n            </ul>\n        </div>\n        {% endif %}\n    </div>\n\n    {% if preview.household_count > 0 and not preview.blockers %}\n    <div class="card danger-box">\n        <h3>XÁC NHẬN XÓA</h3>\n        <p>\n            Hệ thống sẽ <strong>backup database trước khi xóa</strong>.\n            Sau đó xóa đúng cây dữ liệu hộ dân của khoảng ngày đã chọn trong một transaction.\n        </p>\n        <form method="post" action="/cong-cu-du-lieu/don-dep-dieu-tra/xoa">\n            <input type="hidden" name="from_date" value="{{ preview.from_date }}">\n            <input type="hidden" name="to_date" value="{{ preview.to_date }}">\n\n            <label>Nhập chính xác câu xác nhận:</label>\n            <p><code>XOA DU LIEU DIEU TRA</code></p>\n            <input\n                type="text"\n                name="confirm_text"\n                autocomplete="off"\n                placeholder="XOA DU LIEU DIEU TRA"\n                required\n            >\n\n            <div class="actions">\n                <button class="btn danger" type="submit">XÓA DỮ LIỆU HỘ DÂN TRONG KHOẢNG NGÀY</button>\n            </div>\n        </form>\n    </div>\n    {% endif %}\n    {% endif %}\n</div>\n</body>\n</html>\n'

MAIN_MARK_START = "# === BATCH23_SURVEY_CLEANUP_START ==="
MAIN_MARK_END = "# === BATCH23_SURVEY_CLEANUP_END ==="
TARGET_HREF = "/cong-cu-du-lieu/don-dep-dieu-tra"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def log(f, *parts):
    s = " ".join(str(x) for x in parts)
    print(s)
    f.write(s + "\n")
    f.flush()


def validate_db():
    sha = sha256_file(DB)
    if sha != EXPECTED_DB_SHA:
        raise RuntimeError(
            "DB SHA khác nền đã khóa sau khi hoàn thành sáp nhập. "
            "Dừng để không cài trên DB khác."
        )

    con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True, timeout=30)
    try:
        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
        fk = con.execute("PRAGMA foreign_key_check").fetchall()
        tables = {
            str(r[0])
            for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        household_cols = {
            str(r[1])
            for r in con.execute('PRAGMA table_info("households")').fetchall()
        }
    finally:
        con.close()

    if integrity != "ok" or fk:
        raise RuntimeError(
            f"DB health không đạt: integrity={integrity}, fk={len(fk)}"
        )

    required_tables = {"households", "survey_people", "survey_forms"}
    missing = sorted(required_tables - tables)
    if missing:
        raise RuntimeError(f"Thiếu bảng điều tra bắt buộc: {missing}")

    if not any(x in household_cols for x in ("created_at", "created_on", "inserted_at")):
        raise RuntimeError(
            "households không có cột ngày tạo an toàn để lọc theo Từ ngày–Đến ngày."
        )

    return sha, integrity, len(fk)


def backup_source(paths, root):
    backups = {}
    for p in paths:
        if not p.exists():
            continue
        dst = root / p.relative_to(ROOT)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, dst)
        backups[p] = dst
    return backups


def restore_source(backups):
    for target, backup in backups.items():
        shutil.copy2(backup, target)


def patch_main(text):
    if MAIN_MARK_START in text and MAIN_MARK_END in text:
        return text, "ALREADY_PRESENT"

    patch = (
        "\n\n"
        + MAIN_MARK_START + "\n"
        + "from app.routers import survey_cleanup_safe as _survey_cleanup_safe\n"
        + "app.include_router(_survey_cleanup_safe.router)\n"
        + MAIN_MARK_END + "\n"
    )
    return text.rstrip() + patch, "ADDED"


def patch_menu(text):
    # Nếu menu đã trỏ đúng thì thôi.
    if re.search(
        r'href\s*=\s*["\']' + re.escape(TARGET_HREF) + r'["\']',
        text,
        flags=re.I,
    ):
        return text, "ALREADY_PRESENT"

    # Tìm anchor chứa nhãn 1.3.1 Dọn dẹp dữ liệu điều tra rồi chỉ thay href.
    pattern = re.compile(
        r'(?is)(<a\b[^>]*href\s*=\s*)(["\'])(.*?)(\2)([^>]*>\s*'
        r'(?:1\.3\.1\.\s*)?Dọn dẹp dữ liệu điều tra\s*</a>)'
    )
    m = pattern.search(text)
    if not m:
        raise RuntimeError(
            "Không tìm thấy mục menu '1.3.1. Dọn dẹp dữ liệu điều tra'."
        )

    replacement = (
        m.group(1) + '"' + TARGET_HREF + '"' + m.group(5)
    )
    text = text[:m.start()] + replacement + text[m.end():]
    return text, "UPDATED_1_3_1"


def main():
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ROUTER.parent.mkdir(parents=True, exist_ok=True)
    TEMPLATE.parent.mkdir(parents=True, exist_ok=True)

    with OUT.open("w", encoding="utf-8-sig", newline="\n") as f:
        log(f, "=" * 160)
        log(f, "BATCH 23 - CÀI CHỨC NĂNG XÓA DỮ LIỆU ĐIỀU TRA THEO TỪ NGÀY / ĐẾN NGÀY")
        log(f, "CHỈ XÓA CÂY DỮ LIỆU HỘ DÂN; KHÔNG XÓA TRƯỜNG/LỚP/GV/HS ĐỐI CHIẾU")
        log(f, "=" * 160)

        sha, integrity, fk_count = validate_db()
        log(f, "DB_SHA =", sha)
        log(f, "INTEGRITY =", integrity)
        log(f, "FK =", fk_count)

        if not MAIN.exists() or not MENU.exists():
            raise RuntimeError("Thiếu app/main.py hoặc dropdown_menu_v1.html.")

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_root = BACKUP_DIR / f"source_truoc_BATCH23_{ts}"
        backups = backup_source(
            [MAIN, MENU, ROUTER, TEMPLATE],
            backup_root,
        )
        log(f, "SOURCE_BACKUP_DIR =", backup_root)

        main_existed = MAIN.exists()
        menu_existed = MENU.exists()
        router_existed = ROUTER.exists()
        template_existed = TEMPLATE.exists()

        try:
            ROUTER.write_text(ROUTER_CODE, encoding="utf-8")
            TEMPLATE.write_text(TEMPLATE_CODE, encoding="utf-8")

            main_text = MAIN.read_text(encoding="utf-8")
            main_text, main_status = patch_main(main_text)
            MAIN.write_text(main_text, encoding="utf-8")
            log(f, "PATCH main.py =", main_status)

            menu_text = MENU.read_text(encoding="utf-8")
            menu_text, menu_status = patch_menu(menu_text)
            MENU.write_text(menu_text, encoding="utf-8")
            log(f, "PATCH menu 1.3.1 =", menu_status)

            py_compile.compile(str(ROUTER), doraise=True)
            py_compile.compile(str(MAIN), doraise=True)
            log(f, "PY_COMPILE = PASS")

            verify_router = ROUTER.read_text(encoding="utf-8")
            required_router = [
                'PATH = "/cong-cu-du-lieu/don-dep-dieu-tra"',
                'PROTECTED_EXACT',
                'student_reconciliation_source_states',
                '@router.post(PATH + "/xem-truoc")',
                '@router.post(PATH + "/xoa")',
                '_backup_db()',
                'BEGIN IMMEDIATE',
                'PRAGMA foreign_key_check',
                'DELETE FROM "households"',
            ]
            missing_router = [x for x in required_router if x not in verify_router]
            if missing_router:
                raise RuntimeError(
                    f"Router thiếu khóa an toàn: {missing_router}"
                )

            verify_menu = MENU.read_text(encoding="utf-8")
            if TARGET_HREF not in verify_menu:
                raise RuntimeError("Menu 1.3.1 chưa trỏ đến chức năng mới.")

            verify_main = MAIN.read_text(encoding="utf-8")
            if MAIN_MARK_START not in verify_main:
                raise RuntimeError("main.py chưa đăng ký router.")

            log(f, "SOURCE_VERIFY = PASS")

        except Exception:
            restore_source(backups)

            # Nếu file mới chưa từng tồn tại thì xóa file cài dở.
            if not router_existed and ROUTER.exists() and ROUTER not in backups:
                ROUTER.unlink()
            if not template_existed and TEMPLATE.exists() and TEMPLATE not in backups:
                TEMPLATE.unlink()

            log(f, "ROLLBACK_SOURCE = PASS")
            raise

        log(f, "DB_SHA_AFTER_INSTALL =", sha256_file(DB))
        log(f, "DATABASE_WRITES_THIS_RUN = 0")
        log(f, "BATCH_23_SUCCESS = YES")
        log(f, "URL = http://127.0.0.1:8000/cong-cu-du-lieu/don-dep-dieu-tra")
        log(f, "MENU = 1. Danh mục -> 1.3. Công cụ dữ liệu -> 1.3.1. Dọn dẹp dữ liệu điều tra")
        log(f, "")
        log(f, "CÁCH DÙNG = Chọn Từ ngày / Đến ngày -> XEM TRƯỚC -> kiểm tra số hộ/dòng -> nhập XOA DU LIEU DIEU TRA -> XÓA.")
        log(f, "AN_TOAN = Mỗi lần xóa tự backup DB; nếu có phụ thuộc ngoài nhóm hộ dân thì DỪNG, không cố xóa.")
        log(f, "=" * 160)

    return 0


if __name__ == "__main__":
    try:
        rc = main()
    except Exception as exc:
        try:
            EXPORT_DIR.mkdir(parents=True, exist_ok=True)
            with OUT.open("a", encoding="utf-8-sig", newline="\n") as f:
                log(f, "")
                log(f, "=" * 160)
                log(f, "BATCH_23_SUCCESS = NO")
                log(f, "ERROR =", repr(exc))
                if DB.exists():
                    log(f, "DB_SHA_CURRENT =", sha256_file(DB))
                log(f, "DỪNG AN TOÀN.")
                log(f, "=" * 160)
        except Exception:
            print("ERROR =", repr(exc))
        rc = 1

    sys.exit(rc)
