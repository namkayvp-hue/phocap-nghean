from __future__ import annotations

import os
import shutil
import sqlite3
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path

PROJECT = Path(os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")).resolve()
APP = PROJECT / "app"

ROUTER = APP / "routers" / "survey_team_registration.py"
COMMUNE_TPL = APP / "templates" / "survey_teams" / "commune_submissions.html"
BUILDER_TPL = APP / "templates" / "survey_teams" / "commune_team_builder.html"
DETAIL_TPL = APP / "templates" / "survey_teams" / "commune_team_detail.html"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = PROJECT / "exports" / f"backup_bai_13b_10_v2_{STAMP}"

MARKER = "BAI_13B_10_V2_RANDOM_TEAMS_START"
COMMUNE_BUTTON_MARKER = "BAI_13B_10_V2_COMMUNE_BUTTON"

ROUTER_BLOCK = '\n# =========================================================\n# BAI_13B_10_V2_RANDOM_TEAMS_START\n# GHÉP TỔ 3 CẤP + CHIA ĐỀU HỘ Ở TRẠNG THÁI DỰ THẢO\n# =========================================================\n\nTEAM_SCHEMA_SQL = [\n    """\n    CREATE TABLE IF NOT EXISTS survey_investigation_teams (\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        survey_batch_id INTEGER NOT NULL,\n        commune_id INTEGER NOT NULL,\n        team_number INTEGER NOT NULL,\n        status VARCHAR(20) NOT NULL DEFAULT \'DRAFT\',\n        generation_code VARCHAR(60) NOT NULL,\n        created_by_user_id INTEGER NULL,\n        created_at DATETIME NOT NULL,\n        updated_at DATETIME NOT NULL,\n        UNIQUE(survey_batch_id, team_number),\n        FOREIGN KEY(survey_batch_id) REFERENCES survey_batches(id),\n        FOREIGN KEY(commune_id) REFERENCES communes(id),\n        FOREIGN KEY(created_by_user_id) REFERENCES users(id)\n    )\n    """,\n    """\n    CREATE TABLE IF NOT EXISTS survey_investigation_team_members (\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        team_id INTEGER NOT NULL,\n        user_id INTEGER NOT NULL,\n        school_id INTEGER NOT NULL,\n        level_code VARCHAR(20) NOT NULL,\n        order_number INTEGER NOT NULL,\n        created_at DATETIME NOT NULL,\n        UNIQUE(team_id, user_id),\n        UNIQUE(team_id, level_code),\n        FOREIGN KEY(team_id) REFERENCES survey_investigation_teams(id)\n            ON DELETE CASCADE,\n        FOREIGN KEY(user_id) REFERENCES users(id),\n        FOREIGN KEY(school_id) REFERENCES schools(id)\n    )\n    """,\n    """\n    CREATE TABLE IF NOT EXISTS survey_investigation_team_forms (\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        team_id INTEGER NOT NULL,\n        survey_form_id INTEGER NOT NULL,\n        assignment_order INTEGER NOT NULL,\n        created_at DATETIME NOT NULL,\n        UNIQUE(survey_form_id),\n        UNIQUE(team_id, assignment_order),\n        FOREIGN KEY(team_id) REFERENCES survey_investigation_teams(id)\n            ON DELETE CASCADE,\n        FOREIGN KEY(survey_form_id) REFERENCES survey_forms(id)\n    )\n    """,\n    """\n    CREATE TABLE IF NOT EXISTS survey_team_generation_logs (\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        survey_batch_id INTEGER NOT NULL,\n        commune_id INTEGER NOT NULL,\n        generation_code VARCHAR(60) NOT NULL,\n        action VARCHAR(30) NOT NULL,\n        team_count INTEGER NOT NULL DEFAULT 0,\n        household_count INTEGER NOT NULL DEFAULT 0,\n        mn_count INTEGER NOT NULL DEFAULT 0,\n        th_count INTEGER NOT NULL DEFAULT 0,\n        thcs_count INTEGER NOT NULL DEFAULT 0,\n        reserve_count INTEGER NOT NULL DEFAULT 0,\n        actor_user_id INTEGER NULL,\n        actor_name_snapshot VARCHAR(200) NULL,\n        notes TEXT NULL,\n        created_at DATETIME NOT NULL\n    )\n    """,\n    """\n    CREATE INDEX IF NOT EXISTS ix_survey_investigation_teams_batch\n    ON survey_investigation_teams(survey_batch_id, status)\n    """,\n    """\n    CREATE INDEX IF NOT EXISTS ix_survey_investigation_team_members_team\n    ON survey_investigation_team_members(team_id, level_code)\n    """,\n    """\n    CREATE INDEX IF NOT EXISTS ix_survey_investigation_team_forms_team\n    ON survey_investigation_team_forms(team_id, assignment_order)\n    """,\n]\n\n\ndef _ensure_team_schema(db: Session) -> None:\n    for statement in TEAM_SCHEMA_SQL:\n        db.execute(text(statement))\n\n\ndef _commune_batch_scope(\n    db: Session,\n    request: Request,\n    batch_id: int,\n) -> dict[str, Any] | None:\n    if _role(request) != COMMUNE_ROLE_CODE:\n        return None\n\n    user = _user(request)\n    commune_id = user.get("commune_id")\n    if commune_id is None:\n        return None\n\n    batch = _batch_row(db, int(batch_id))\n    if batch is None:\n        return None\n\n    if int(batch["commune_id"]) != int(commune_id):\n        return None\n\n    return batch\n\n\ndef _sent_participants(\n    db: Session,\n    *,\n    batch_id: int,\n) -> list[dict[str, Any]]:\n    rows = db.execute(\n        text(\n            """\n            SELECT\n                sip.user_id,\n                sip.school_id,\n                sip.level_code,\n                u.full_name,\n                u.username,\n                s.name AS school_name\n            FROM survey_investigation_participants AS sip\n            JOIN survey_participant_submissions AS sps\n              ON sps.survey_batch_id = sip.survey_batch_id\n             AND sps.school_id = sip.school_id\n             AND sps.status = \'SENT\'\n            JOIN users AS u\n              ON u.id = sip.user_id\n             AND u.is_active = 1\n            JOIN schools AS s\n              ON s.id = sip.school_id\n             AND s.is_active = 1\n            WHERE sip.survey_batch_id = :batch_id\n              AND sip.level_code IN (\'MN\', \'TH\', \'THCS\')\n            ORDER BY\n                sip.level_code,\n                s.name COLLATE NOCASE,\n                u.full_name COLLATE NOCASE,\n                u.id\n            """\n        ),\n        {"batch_id": int(batch_id)},\n    ).mappings().all()\n\n    return [dict(row) for row in rows]\n\n\ndef _batch_forms(\n    db: Session,\n    *,\n    batch_id: int,\n) -> list[dict[str, Any]]:\n    rows = db.execute(\n        text(\n            """\n            SELECT\n                sf.id AS survey_form_id,\n                sf.form_number,\n                h.id AS household_id,\n                h.code AS household_code,\n                h.head_name,\n                h.hamlet_name,\n                h.address\n            FROM survey_forms AS sf\n            JOIN households AS h\n              ON h.id = sf.household_id\n            WHERE sf.survey_batch_id = :batch_id\n            ORDER BY\n                COALESCE(h.hamlet_name, \'\') COLLATE NOCASE,\n                h.head_name COLLATE NOCASE,\n                sf.id\n            """\n        ),\n        {"batch_id": int(batch_id)},\n    ).mappings().all()\n\n    return [dict(row) for row in rows]\n\n\ndef _draft_team_exists(\n    db: Session,\n    *,\n    batch_id: int,\n) -> bool:\n    value = db.execute(\n        text(\n            """\n            SELECT 1\n            FROM survey_investigation_teams\n            WHERE survey_batch_id = :batch_id\n            LIMIT 1\n            """\n        ),\n        {"batch_id": int(batch_id)},\n    ).scalar()\n    return value is not None\n\n\ndef _delete_draft_teams(\n    db: Session,\n    *,\n    batch_id: int,\n) -> None:\n    team_ids = [\n        int(value)\n        for value in db.execute(\n            text(\n                """\n                SELECT id\n                FROM survey_investigation_teams\n                WHERE survey_batch_id = :batch_id\n                  AND status = \'DRAFT\'\n                """\n            ),\n            {"batch_id": int(batch_id)},\n        ).scalars().all()\n    ]\n\n    if not team_ids:\n        return\n\n    placeholders = ", ".join(\n        f":team_id_{index}"\n        for index in range(len(team_ids))\n    )\n    params = {\n        f"team_id_{index}": team_id\n        for index, team_id in enumerate(team_ids)\n    }\n\n    db.execute(\n        text(\n            f"""\n            DELETE FROM survey_investigation_team_forms\n            WHERE team_id IN ({placeholders})\n            """\n        ),\n        params,\n    )\n    db.execute(\n        text(\n            f"""\n            DELETE FROM survey_investigation_team_members\n            WHERE team_id IN ({placeholders})\n            """\n        ),\n        params,\n    )\n    db.execute(\n        text(\n            f"""\n            DELETE FROM survey_investigation_teams\n            WHERE id IN ({placeholders})\n            """\n        ),\n        params,\n    )\n\n\ndef _generation_log(\n    db: Session,\n    *,\n    request: Request,\n    batch_id: int,\n    commune_id: int,\n    generation_code: str,\n    action: str,\n    team_count: int,\n    household_count: int,\n    mn_count: int,\n    th_count: int,\n    thcs_count: int,\n    reserve_count: int,\n    notes: str = "",\n) -> None:\n    user = _user(request)\n    db.execute(\n        text(\n            """\n            INSERT INTO survey_team_generation_logs (\n                survey_batch_id,\n                commune_id,\n                generation_code,\n                action,\n                team_count,\n                household_count,\n                mn_count,\n                th_count,\n                thcs_count,\n                reserve_count,\n                actor_user_id,\n                actor_name_snapshot,\n                notes,\n                created_at\n            ) VALUES (\n                :batch_id,\n                :commune_id,\n                :generation_code,\n                :action,\n                :team_count,\n                :household_count,\n                :mn_count,\n                :th_count,\n                :thcs_count,\n                :reserve_count,\n                :actor_user_id,\n                :actor_name_snapshot,\n                :notes,\n                :created_at\n            )\n            """\n        ),\n        {\n            "batch_id": int(batch_id),\n            "commune_id": int(commune_id),\n            "generation_code": generation_code,\n            "action": action,\n            "team_count": int(team_count),\n            "household_count": int(household_count),\n            "mn_count": int(mn_count),\n            "th_count": int(th_count),\n            "thcs_count": int(thcs_count),\n            "reserve_count": int(reserve_count),\n            "actor_user_id": user.get("id"),\n            "actor_name_snapshot": str(\n                user.get("full_name") or ""\n            )[:200] or None,\n            "notes": notes[:2000] or None,\n            "created_at": datetime.now().isoformat(\n                sep=" ",\n                timespec="seconds",\n            ),\n        },\n    )\n\n\ndef _team_preview_data(\n    db: Session,\n    *,\n    batch_id: int,\n) -> dict[str, Any]:\n    participants = _sent_participants(\n        db,\n        batch_id=batch_id,\n    )\n\n    by_level = {\n        "MN": [],\n        "TH": [],\n        "THCS": [],\n    }\n    for item in participants:\n        level_code = str(item.get("level_code") or "")\n        if level_code in by_level:\n            by_level[level_code].append(item)\n\n    team_rows = db.execute(\n        text(\n            """\n            SELECT\n                t.id,\n                t.team_number,\n                t.status,\n                t.generation_code,\n                t.created_at,\n                COUNT(tf.id) AS household_count\n            FROM survey_investigation_teams AS t\n            LEFT JOIN survey_investigation_team_forms AS tf\n              ON tf.team_id = t.id\n            WHERE t.survey_batch_id = :batch_id\n            GROUP BY\n                t.id,\n                t.team_number,\n                t.status,\n                t.generation_code,\n                t.created_at\n            ORDER BY t.team_number\n            """\n        ),\n        {"batch_id": int(batch_id)},\n    ).mappings().all()\n\n    teams: list[dict[str, Any]] = []\n    used_user_ids: set[int] = set()\n\n    for raw_team in team_rows:\n        team = dict(raw_team)\n\n        member_rows = db.execute(\n            text(\n                """\n                SELECT\n                    tm.user_id,\n                    tm.level_code,\n                    tm.order_number,\n                    u.full_name,\n                    u.username,\n                    s.name AS school_name\n                FROM survey_investigation_team_members AS tm\n                JOIN users AS u ON u.id = tm.user_id\n                JOIN schools AS s ON s.id = tm.school_id\n                WHERE tm.team_id = :team_id\n                ORDER BY tm.order_number\n                """\n            ),\n            {"team_id": int(team["id"])},\n        ).mappings().all()\n\n        members = [dict(row) for row in member_rows]\n        for item in members:\n            used_user_ids.add(int(item["user_id"]))\n\n        hamlet_rows = db.execute(\n            text(\n                """\n                SELECT\n                    COALESCE(h.hamlet_name, \'Chưa xác định\') AS hamlet_name,\n                    COUNT(*) AS household_count\n                FROM survey_investigation_team_forms AS tf\n                JOIN survey_forms AS sf\n                  ON sf.id = tf.survey_form_id\n                JOIN households AS h\n                  ON h.id = sf.household_id\n                WHERE tf.team_id = :team_id\n                GROUP BY COALESCE(h.hamlet_name, \'Chưa xác định\')\n                ORDER BY\n                    household_count DESC,\n                    hamlet_name COLLATE NOCASE\n                """\n            ),\n            {"team_id": int(team["id"])},\n        ).mappings().all()\n\n        team["members"] = members\n        team["hamlet_summary"] = [\n            dict(row) for row in hamlet_rows\n        ]\n        teams.append(team)\n\n    reserve: list[dict[str, Any]] = []\n    for item in participants:\n        if int(item["user_id"]) not in used_user_ids:\n            reserve.append(item)\n\n    form_total = len(\n        _batch_forms(\n            db,\n            batch_id=batch_id,\n        )\n    )\n    team_count = len(teams)\n    counts = [\n        int(item.get("household_count") or 0)\n        for item in teams\n    ]\n\n    return {\n        "teams": teams,\n        "reserve": reserve,\n        "form_total": form_total,\n        "team_count": team_count,\n        "mn_count": len(by_level["MN"]),\n        "th_count": len(by_level["TH"]),\n        "thcs_count": len(by_level["THCS"]),\n        "possible_team_count": min(\n            len(by_level["MN"]),\n            len(by_level["TH"]),\n            len(by_level["THCS"]),\n        ) if all(by_level.values()) else 0,\n        "min_households": min(counts) if counts else 0,\n        "max_households": max(counts) if counts else 0,\n    }\n\n\n@router.get("/lap-to", response_class=HTMLResponse)\ndef commune_team_builder_page(\n    request: Request,\n    batch_id: int | None = None,\n    status: str | None = None,\n    db: Session = Depends(get_db),\n):\n    if _role(request) != COMMUNE_ROLE_CODE:\n        return _forbidden()\n\n    _ensure_schema(db)\n    _ensure_team_schema(db)\n\n    user = _user(request)\n    commune_id = user.get("commune_id")\n    if commune_id is None:\n        return _forbidden()\n\n    batches = _available_batches(\n        db,\n        commune_id=int(commune_id),\n    )\n    batch = _selected_batch(\n        db,\n        commune_id=int(commune_id),\n        batch_id=batch_id,\n    )\n\n    preview = {\n        "teams": [],\n        "reserve": [],\n        "form_total": 0,\n        "team_count": 0,\n        "mn_count": 0,\n        "th_count": 0,\n        "thcs_count": 0,\n        "possible_team_count": 0,\n        "min_households": 0,\n        "max_households": 0,\n    }\n\n    if batch is not None:\n        preview = _team_preview_data(\n            db,\n            batch_id=int(batch["id"]),\n        )\n\n    status_messages = {\n        "generated": (\n            "Đã tạo dự thảo tổ 3 cấp và chia đều hộ dân. "\n            "Phân công hiện CHƯA gửi xuống trường/giáo viên."\n        ),\n        "regenerated": (\n            "Đã tạo lại dự thảo tổ và phân bổ lại hộ dân."\n        ),\n        "cleared": (\n            "Đã xóa bản dự thảo tổ. "\n            "Danh sách giáo viên các trường vẫn được giữ nguyên."\n        ),\n        "not_ready": (\n            "Chưa đủ giáo viên đã gửi ở cả 3 cấp MN, TH và THCS "\n            "để tạo tổ."\n        ),\n        "no_household": (\n            "Đợt điều tra chưa có hộ/phiếu để phân công."\n        ),\n    }\n\n    return templates.TemplateResponse(\n        request=request,\n        name="survey_teams/commune_team_builder.html",\n        context={\n            "nguoi_dung": user,\n            "batches": batches,\n            "batch": batch,\n            "preview": preview,\n            "message": status_messages.get(status),\n        },\n    )\n\n\n@router.post("/lap-to/tao-ngau-nhien")\nasync def generate_random_teams(\n    request: Request,\n    db: Session = Depends(get_db),\n):\n    if _role(request) != COMMUNE_ROLE_CODE:\n        return _forbidden()\n\n    _ensure_schema(db)\n    _ensure_team_schema(db)\n\n    form = await request.form()\n    try:\n        batch_id = int(form.get("batch_id") or 0)\n    except (TypeError, ValueError):\n        batch_id = 0\n\n    batch = _commune_batch_scope(\n        db,\n        request,\n        batch_id,\n    )\n    if batch is None:\n        return _forbidden()\n\n    participants = _sent_participants(\n        db,\n        batch_id=batch_id,\n    )\n    forms = _batch_forms(\n        db,\n        batch_id=batch_id,\n    )\n\n    by_level = {\n        "MN": [],\n        "TH": [],\n        "THCS": [],\n    }\n    for item in participants:\n        level_code = str(item.get("level_code") or "")\n        if level_code in by_level:\n            by_level[level_code].append(item)\n\n    if not forms:\n        return RedirectResponse(\n            url=(\n                "/dieu-tra/phan-cong-to-dieu-tra/lap-to"\n                f"?batch_id={batch_id}&status=no_household"\n            ),\n            status_code=303,\n        )\n\n    if not all(by_level.values()):\n        return RedirectResponse(\n            url=(\n                "/dieu-tra/phan-cong-to-dieu-tra/lap-to"\n                f"?batch_id={batch_id}&status=not_ready"\n            ),\n            status_code=303,\n        )\n\n    team_count = min(\n        len(by_level["MN"]),\n        len(by_level["TH"]),\n        len(by_level["THCS"]),\n    )\n    if team_count <= 0:\n        return RedirectResponse(\n            url=(\n                "/dieu-tra/phan-cong-to-dieu-tra/lap-to"\n                f"?batch_id={batch_id}&status=not_ready"\n            ),\n            status_code=303,\n        )\n\n    # Không cho ghi đè tổ đã chốt ở V3.\n    locked_exists = db.execute(\n        text(\n            """\n            SELECT 1\n            FROM survey_investigation_teams\n            WHERE survey_batch_id = :batch_id\n              AND status != \'DRAFT\'\n            LIMIT 1\n            """\n        ),\n        {"batch_id": batch_id},\n    ).scalar()\n    if locked_exists is not None:\n        return RedirectResponse(\n            url=(\n                "/dieu-tra/phan-cong-to-dieu-tra/lap-to"\n                f"?batch_id={batch_id}"\n            ),\n            status_code=303,\n        )\n\n    # Nếu đã có dự thảo, xóa dự thảo cũ để tạo lại.\n    existed_before = _draft_team_exists(\n        db,\n        batch_id=batch_id,\n    )\n    _delete_draft_teams(\n        db,\n        batch_id=batch_id,\n    )\n\n    now = datetime.now()\n    generation_code = (\n        f"GEN-{batch_id}-"\n        f"{now.strftime(\'%Y%m%d%H%M%S%f\')}"\n    )\n\n    # Seed được lưu gián tiếp trong generation_code để lần tạo đã lưu\n    # không thay đổi khi người dùng mở lại trang.\n    import random\n    seed_value = (\n        int(now.timestamp() * 1_000_000)\n        ^ int(_user(request).get("id") or 0)\n        ^ int(batch_id)\n    )\n    rng = random.Random(seed_value)\n\n    for level_code in ("MN", "TH", "THCS"):\n        rng.shuffle(by_level[level_code])\n\n    rng.shuffle(forms)\n\n    created_at = now.isoformat(\n        sep=" ",\n        timespec="seconds",\n    )\n\n    team_ids: list[int] = []\n\n    for index in range(team_count):\n        cursor = db.execute(\n            text(\n                """\n                INSERT INTO survey_investigation_teams (\n                    survey_batch_id,\n                    commune_id,\n                    team_number,\n                    status,\n                    generation_code,\n                    created_by_user_id,\n                    created_at,\n                    updated_at\n                ) VALUES (\n                    :batch_id,\n                    :commune_id,\n                    :team_number,\n                    \'DRAFT\',\n                    :generation_code,\n                    :created_by_user_id,\n                    :created_at,\n                    :updated_at\n                )\n                """\n            ),\n            {\n                "batch_id": batch_id,\n                "commune_id": int(batch["commune_id"]),\n                "team_number": index + 1,\n                "generation_code": generation_code,\n                "created_by_user_id": _user(request).get("id"),\n                "created_at": created_at,\n                "updated_at": created_at,\n            },\n        )\n        team_id = int(cursor.lastrowid)\n        team_ids.append(team_id)\n\n        members = (\n            ("MN", by_level["MN"][index], 1),\n            ("TH", by_level["TH"][index], 2),\n            ("THCS", by_level["THCS"][index], 3),\n        )\n\n        for level_code, member, order_number in members:\n            db.execute(\n                text(\n                    """\n                    INSERT INTO survey_investigation_team_members (\n                        team_id,\n                        user_id,\n                        school_id,\n                        level_code,\n                        order_number,\n                        created_at\n                    ) VALUES (\n                        :team_id,\n                        :user_id,\n                        :school_id,\n                        :level_code,\n                        :order_number,\n                        :created_at\n                    )\n                    """\n                ),\n                {\n                    "team_id": team_id,\n                    "user_id": int(member["user_id"]),\n                    "school_id": int(member["school_id"]),\n                    "level_code": level_code,\n                    "order_number": order_number,\n                    "created_at": created_at,\n                },\n            )\n\n    # Chia vòng tròn: chênh lệch số hộ giữa các tổ tối đa 1.\n    team_assignment_order = {\n        team_id: 0\n        for team_id in team_ids\n    }\n\n    for index, form_row in enumerate(forms):\n        team_id = team_ids[index % team_count]\n        team_assignment_order[team_id] += 1\n\n        db.execute(\n            text(\n                """\n                INSERT INTO survey_investigation_team_forms (\n                    team_id,\n                    survey_form_id,\n                    assignment_order,\n                    created_at\n                ) VALUES (\n                    :team_id,\n                    :survey_form_id,\n                    :assignment_order,\n                    :created_at\n                )\n                """\n            ),\n            {\n                "team_id": team_id,\n                "survey_form_id": int(\n                    form_row["survey_form_id"]\n                ),\n                "assignment_order": int(\n                    team_assignment_order[team_id]\n                ),\n                "created_at": created_at,\n            },\n        )\n\n    # Kiểm tra toàn vẹn trước commit.\n    assigned_count = int(\n        db.execute(\n            text(\n                """\n                SELECT COUNT(*)\n                FROM survey_investigation_team_forms AS tf\n                JOIN survey_investigation_teams AS t\n                  ON t.id = tf.team_id\n                WHERE t.survey_batch_id = :batch_id\n                """\n            ),\n            {"batch_id": batch_id},\n        ).scalar()\n        or 0\n    )\n\n    member_count = int(\n        db.execute(\n            text(\n                """\n                SELECT COUNT(*)\n                FROM survey_investigation_team_members AS tm\n                JOIN survey_investigation_teams AS t\n                  ON t.id = tm.team_id\n                WHERE t.survey_batch_id = :batch_id\n                """\n            ),\n            {"batch_id": batch_id},\n        ).scalar()\n        or 0\n    )\n\n    if assigned_count != len(forms):\n        db.rollback()\n        raise RuntimeError(\n            "Không phân đủ toàn bộ phiếu/hộ cho các tổ."\n        )\n\n    if member_count != team_count * 3:\n        db.rollback()\n        raise RuntimeError(\n            "Một hoặc nhiều tổ chưa đủ đúng 3 thành viên."\n        )\n\n    reserve_count = (\n        len(by_level["MN"])\n        + len(by_level["TH"])\n        + len(by_level["THCS"])\n        - team_count * 3\n    )\n\n    _generation_log(\n        db,\n        request=request,\n        batch_id=batch_id,\n        commune_id=int(batch["commune_id"]),\n        generation_code=generation_code,\n        action=(\n            "REGENERATE_DRAFT"\n            if existed_before\n            else "GENERATE_DRAFT"\n        ),\n        team_count=team_count,\n        household_count=len(forms),\n        mn_count=len(by_level["MN"]),\n        th_count=len(by_level["TH"]),\n        thcs_count=len(by_level["THCS"]),\n        reserve_count=reserve_count,\n        notes=(\n            f"Seed={seed_value}; "\n            "chia vòng tròn sau khi xáo trộn danh sách hộ."\n        ),\n    )\n\n    db.commit()\n\n    return RedirectResponse(\n        url=(\n            "/dieu-tra/phan-cong-to-dieu-tra/lap-to"\n            f"?batch_id={batch_id}&status="\n            + (\n                "regenerated"\n                if existed_before\n                else "generated"\n            )\n        ),\n        status_code=303,\n    )\n\n\n@router.post("/lap-to/xoa-du-thao")\nasync def clear_team_draft(\n    request: Request,\n    db: Session = Depends(get_db),\n):\n    if _role(request) != COMMUNE_ROLE_CODE:\n        return _forbidden()\n\n    _ensure_schema(db)\n    _ensure_team_schema(db)\n\n    form = await request.form()\n    try:\n        batch_id = int(form.get("batch_id") or 0)\n    except (TypeError, ValueError):\n        batch_id = 0\n\n    batch = _commune_batch_scope(\n        db,\n        request,\n        batch_id,\n    )\n    if batch is None:\n        return _forbidden()\n\n    locked_exists = db.execute(\n        text(\n            """\n            SELECT 1\n            FROM survey_investigation_teams\n            WHERE survey_batch_id = :batch_id\n              AND status != \'DRAFT\'\n            LIMIT 1\n            """\n        ),\n        {"batch_id": batch_id},\n    ).scalar()\n\n    if locked_exists is None:\n        _delete_draft_teams(\n            db,\n            batch_id=batch_id,\n        )\n\n    _generation_log(\n        db,\n        request=request,\n        batch_id=batch_id,\n        commune_id=int(batch["commune_id"]),\n        generation_code=(\n            f"CLEAR-{batch_id}-"\n            f"{datetime.now().strftime(\'%Y%m%d%H%M%S%f\')}"\n        ),\n        action="CLEAR_DRAFT",\n        team_count=0,\n        household_count=0,\n        mn_count=0,\n        th_count=0,\n        thcs_count=0,\n        reserve_count=0,\n        notes="Xóa dự thảo trước khi chốt phân công.",\n    )\n\n    db.commit()\n\n    return RedirectResponse(\n        url=(\n            "/dieu-tra/phan-cong-to-dieu-tra/lap-to"\n            f"?batch_id={batch_id}&status=cleared"\n        ),\n        status_code=303,\n    )\n\n\n@router.get(\n    "/lap-to/{team_id}",\n    response_class=HTMLResponse,\n)\ndef commune_team_detail(\n    team_id: int,\n    request: Request,\n    db: Session = Depends(get_db),\n):\n    if _role(request) != COMMUNE_ROLE_CODE:\n        return _forbidden()\n\n    _ensure_team_schema(db)\n\n    user = _user(request)\n    commune_id = user.get("commune_id")\n    if commune_id is None:\n        return _forbidden()\n\n    team = db.execute(\n        text(\n            """\n            SELECT\n                t.id,\n                t.survey_batch_id,\n                t.commune_id,\n                t.team_number,\n                t.status,\n                t.generation_code,\n                sb.name AS batch_name,\n                sy.code AS school_year_code\n            FROM survey_investigation_teams AS t\n            JOIN survey_batches AS sb\n              ON sb.id = t.survey_batch_id\n            JOIN school_years AS sy\n              ON sy.id = sb.school_year_id\n            WHERE t.id = :team_id\n              AND t.commune_id = :commune_id\n            LIMIT 1\n            """\n        ),\n        {\n            "team_id": int(team_id),\n            "commune_id": int(commune_id),\n        },\n    ).mappings().first()\n\n    if team is None:\n        return _forbidden()\n\n    members = [\n        dict(row)\n        for row in db.execute(\n            text(\n                """\n                SELECT\n                    tm.level_code,\n                    tm.order_number,\n                    u.full_name,\n                    u.username,\n                    s.name AS school_name\n                FROM survey_investigation_team_members AS tm\n                JOIN users AS u ON u.id = tm.user_id\n                JOIN schools AS s ON s.id = tm.school_id\n                WHERE tm.team_id = :team_id\n                ORDER BY tm.order_number\n                """\n            ),\n            {"team_id": int(team_id)},\n        ).mappings().all()\n    ]\n\n    households = [\n        dict(row)\n        for row in db.execute(\n            text(\n                """\n                SELECT\n                    tf.assignment_order,\n                    sf.form_number,\n                    h.code AS household_code,\n                    h.head_name,\n                    h.hamlet_name,\n                    h.address,\n                    (\n                        SELECT COUNT(*)\n                        FROM survey_people AS sp\n                        WHERE sp.household_id = h.id\n                          AND sp.is_active = 1\n                    ) AS people_count\n                FROM survey_investigation_team_forms AS tf\n                JOIN survey_forms AS sf\n                  ON sf.id = tf.survey_form_id\n                JOIN households AS h\n                  ON h.id = sf.household_id\n                WHERE tf.team_id = :team_id\n                ORDER BY tf.assignment_order\n                """\n            ),\n            {"team_id": int(team_id)},\n        ).mappings().all()\n    ]\n\n    return templates.TemplateResponse(\n        request=request,\n        name="survey_teams/commune_team_detail.html",\n        context={\n            "nguoi_dung": user,\n            "team": dict(team),\n            "members": members,\n            "households": households,\n        },\n    )\n\n# BAI_13B_10_V2_RANDOM_TEAMS_END\n'
BUILDER_TEMPLATE = '<!DOCTYPE html>\n<html lang="vi">\n<head>\n    <meta charset="UTF-8">\n    <meta name="viewport" content="width=device-width, initial-scale=1.0">\n    <title>Lập tổ điều tra 3 cấp</title>\n    <link rel="stylesheet" href="{{ url_for(\'static\', path=\'/css/style.css\') }}">\n    <style>\n        .wrap{width:min(1480px,96%);margin:24px auto 60px}\n        .panel{background:#fff;border-radius:16px;padding:20px;margin:16px 0;box-shadow:0 8px 24px rgba(30,70,110,.08)}\n        .cards{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:12px}\n        .card{border:1px solid #d8e4ef;border-radius:12px;padding:14px}\n        .card small{display:block;color:#60758a;font-weight:800}\n        .card strong{display:block;font-size:25px;color:#1769aa;margin-top:6px}\n        .team-table{width:100%;border-collapse:collapse;min-width:1080px}\n        .team-table th,.team-table td{padding:11px;border-bottom:1px solid #e4ebf2;text-align:left;vertical-align:top}\n        .team-table th{background:#edf5fc}\n        .scroll{overflow-x:auto}\n        .member{margin:3px 0}\n        .badge{display:inline-block;min-width:48px;font-weight:800;color:#0b5cab}\n        .actions{display:flex;gap:10px;flex-wrap:wrap}\n        .ok{background:#eef9f0;border:1px solid #b7dfbd;color:#246b2c;padding:13px;border-radius:12px}\n        .warn{background:#fff7e6;border:1px solid #ebcf8f;color:#795600;padding:13px;border-radius:12px}\n        .reserve{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}\n        .reserve-item{border:1px solid #e0e6ec;border-radius:10px;padding:10px}\n        select{padding:10px;border:1px solid #c9d6e2;border-radius:9px;min-width:300px}\n        @media(max-width:1000px){.cards{grid-template-columns:repeat(3,1fr)}}\n        @media(max-width:650px){.cards{grid-template-columns:1fr 1fr}.reserve{grid-template-columns:1fr}}\n    </style>\n</head>\n<body>\n{% include "partials/dropdown_menu_v1.html" %}\n\n<main class="wrap">\n    <section class="panel">\n        <p class="admin-eyebrow">TỔ ĐIỀU TRA 3 CẤP · BƯỚC 2</p>\n        <h1>Ghép tổ ngẫu nhiên và chia đều hộ dân</h1>\n        <p>\n            Mỗi tổ gồm đúng <strong>1 GV Mầm non + 1 GV Tiểu học + 1 GV THCS</strong>.\n            Dự thảo này chưa gửi xuống Trường/Giáo viên.\n        </p>\n\n        {% if message %}\n        <div class="ok">{{ message }}</div>\n        {% endif %}\n\n        <form method="get" action="/dieu-tra/phan-cong-to-dieu-tra/lap-to">\n            <label><strong>Đợt điều tra</strong></label><br>\n            <select name="batch_id" onchange="this.form.submit()">\n                {% for item in batches %}\n                <option value="{{ item.id }}" {% if batch and item.id == batch.id %}selected{% endif %}>\n                    {{ item.school_year_code }} · {{ item.name }}\n                </option>\n                {% endfor %}\n            </select>\n        </form>\n    </section>\n\n    {% if batch %}\n    <section class="panel">\n        <div class="cards">\n            <div class="card"><small>GV MN đã gửi</small><strong>{{ preview.mn_count }}</strong></div>\n            <div class="card"><small>GV TH đã gửi</small><strong>{{ preview.th_count }}</strong></div>\n            <div class="card"><small>GV THCS đã gửi</small><strong>{{ preview.thcs_count }}</strong></div>\n            <div class="card"><small>Tổ có thể lập</small><strong>{{ preview.possible_team_count }}</strong></div>\n            <div class="card"><small>Tổng hộ/phiếu</small><strong>{{ preview.form_total }}</strong></div>\n            <div class="card"><small>Tổ đã tạo</small><strong>{{ preview.team_count }}</strong></div>\n        </div>\n\n        {% if preview.possible_team_count == 0 %}\n        <div class="warn" style="margin-top:14px">\n            Chưa đủ danh sách giáo viên đã gửi ở cả 3 cấp MN, TH và THCS.\n            Xã/phường cần chờ các trường gửi đủ trước khi tạo tổ.\n        </div>\n        {% endif %}\n\n        {% if preview.team_count > 0 %}\n        <div class="ok" style="margin-top:14px">\n            Phân bổ hiện tại: mỗi tổ có từ\n            <strong>{{ preview.min_households }}</strong> đến\n            <strong>{{ preview.max_households }}</strong> hộ.\n            Chênh lệch tối đa:\n            <strong>{{ preview.max_households - preview.min_households }}</strong> hộ.\n        </div>\n        {% endif %}\n\n        <div class="actions" style="margin-top:16px">\n            <form method="post" action="/dieu-tra/phan-cong-to-dieu-tra/lap-to/tao-ngau-nhien">\n                <input type="hidden" name="batch_id" value="{{ batch.id }}">\n                <button\n                    class="button button-primary"\n                    type="submit"\n                    {% if preview.possible_team_count == 0 or preview.form_total == 0 %}disabled{% endif %}\n                    onclick="return confirm(\'Tạo ngẫu nhiên các tổ 3 cấp và chia đều toàn bộ hộ? Nếu đang có dự thảo, dự thảo cũ sẽ được tạo lại.\');"\n                >\n                    {% if preview.team_count > 0 %}\n                        🔀 Tạo lại ngẫu nhiên\n                    {% else %}\n                        🎲 Tạo tổ ngẫu nhiên + chia hộ\n                    {% endif %}\n                </button>\n            </form>\n\n            {% if preview.team_count > 0 %}\n            <form method="post" action="/dieu-tra/phan-cong-to-dieu-tra/lap-to/xoa-du-thao">\n                <input type="hidden" name="batch_id" value="{{ batch.id }}">\n                <button\n                    class="button button-secondary"\n                    type="submit"\n                    onclick="return confirm(\'Xóa toàn bộ dự thảo tổ và phân bổ hộ hiện tại? Danh sách GV trường gửi về vẫn được giữ nguyên.\');"\n                >Xóa dự thảo</button>\n            </form>\n            {% endif %}\n\n            <a\n                class="button button-light"\n                href="/dieu-tra/phan-cong-to-dieu-tra/danh-sach-truong?batch_id={{ batch.id }}"\n            >← Danh sách trường gửi về</a>\n        </div>\n    </section>\n\n    {% if preview.team_count > 0 %}\n    <section class="panel">\n        <h2>Xem trước các tổ điều tra</h2>\n        <div class="scroll">\n            <table class="team-table">\n                <thead>\n                    <tr>\n                        <th>Tổ</th>\n                        <th>3 giáo viên</th>\n                        <th>Số hộ</th>\n                        <th>Thôn/xóm</th>\n                        <th>Chi tiết</th>\n                    </tr>\n                </thead>\n                <tbody>\n                {% for team in preview.teams %}\n                    <tr>\n                        <td><strong>Tổ {{ team.team_number }}</strong></td>\n                        <td>\n                            {% for member in team.members %}\n                            <div class="member">\n                                <span class="badge">{{ member.level_code }}</span>\n                                <strong>{{ member.full_name }}</strong>\n                                · {{ member.school_name }}\n                            </div>\n                            {% endfor %}\n                        </td>\n                        <td><strong>{{ team.household_count }}</strong></td>\n                        <td>\n                            {% for item in team.hamlet_summary %}\n                                {{ item.hamlet_name }} ({{ item.household_count }}){% if not loop.last %}, {% endif %}\n                            {% endfor %}\n                        </td>\n                        <td>\n                            <a\n                                class="button button-light"\n                                href="/dieu-tra/phan-cong-to-dieu-tra/lap-to/{{ team.id }}"\n                            >Xem hộ</a>\n                        </td>\n                    </tr>\n                {% endfor %}\n                </tbody>\n            </table>\n        </div>\n    </section>\n    {% endif %}\n\n    {% if preview.reserve %}\n    <section class="panel">\n        <h2>Giáo viên dự phòng / chưa ghép tổ</h2>\n        <p>\n            Do số GV ba cấp không bằng nhau, giáo viên dư được giữ ở danh sách\n            dự phòng, không tự ghép sai cơ cấu tổ.\n        </p>\n        <div class="reserve">\n            {% for item in preview.reserve %}\n            <div class="reserve-item">\n                <strong>{{ item.level_code }} · {{ item.full_name }}</strong><br>\n                {{ item.school_name }}\n            </div>\n            {% endfor %}\n        </div>\n    </section>\n    {% endif %}\n    {% endif %}\n</main>\n</body>\n</html>\n'
DETAIL_TEMPLATE = '<!DOCTYPE html>\n<html lang="vi">\n<head>\n    <meta charset="UTF-8">\n    <meta name="viewport" content="width=device-width, initial-scale=1.0">\n    <title>Chi tiết tổ điều tra</title>\n    <link rel="stylesheet" href="{{ url_for(\'static\', path=\'/css/style.css\') }}">\n    <style>\n        .wrap{width:min(1400px,96%);margin:24px auto 60px}\n        .panel{background:#fff;border-radius:16px;padding:20px;margin:16px 0;box-shadow:0 8px 24px rgba(30,70,110,.08)}\n        .members{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}\n        .member{border:1px solid #d8e4ef;border-radius:12px;padding:14px}\n        .table{width:100%;border-collapse:collapse;min-width:900px}\n        .table th,.table td{padding:10px;border-bottom:1px solid #e4ebf2;text-align:left;vertical-align:top}\n        .table th{background:#edf5fc}\n        .scroll{overflow-x:auto}\n        @media(max-width:800px){.members{grid-template-columns:1fr}}\n    </style>\n</head>\n<body>\n{% include "partials/dropdown_menu_v1.html" %}\n\n<main class="wrap">\n    <section class="panel">\n        <p class="admin-eyebrow">XEM TRƯỚC PHÂN CÔNG</p>\n        <h1>Tổ {{ team.team_number }}</h1>\n        <p>{{ team.school_year_code }} · {{ team.batch_name }} · Trạng thái: {{ team.status }}</p>\n        <a\n            class="button button-light"\n            href="/dieu-tra/phan-cong-to-dieu-tra/lap-to?batch_id={{ team.survey_batch_id }}"\n        >← Danh sách tổ</a>\n    </section>\n\n    <section class="panel">\n        <h2>Thành viên tổ</h2>\n        <div class="members">\n            {% for member in members %}\n            <div class="member">\n                <strong>{{ member.level_code }} · {{ member.full_name }}</strong><br>\n                {{ member.school_name }}<br>\n                <span class="muted">{{ member.username }}</span>\n            </div>\n            {% endfor %}\n        </div>\n    </section>\n\n    <section class="panel">\n        <h2>{{ households|length }} hộ được phân dự thảo</h2>\n        <div class="scroll">\n            <table class="table">\n                <thead>\n                    <tr>\n                        <th>STT</th>\n                        <th>Số phiếu</th>\n                        <th>Mã hộ</th>\n                        <th>Chủ hộ</th>\n                        <th>Thôn/xóm</th>\n                        <th>Địa chỉ</th>\n                        <th>Thành viên</th>\n                    </tr>\n                </thead>\n                <tbody>\n                {% for item in households %}\n                    <tr>\n                        <td>{{ item.assignment_order }}</td>\n                        <td><strong>{{ item.form_number }}</strong></td>\n                        <td>{{ item.household_code }}</td>\n                        <td>{{ item.head_name }}</td>\n                        <td>{{ item.hamlet_name or \'—\' }}</td>\n                        <td>{{ item.address }}</td>\n                        <td>{{ item.people_count }}</td>\n                    </tr>\n                {% else %}\n                    <tr><td colspan="7">Tổ chưa có hộ.</td></tr>\n                {% endfor %}\n                </tbody>\n            </table>\n        </div>\n    </section>\n</main>\n</body>\n</html>\n'

TEAM_SCHEMA_SQL = [
    """
    CREATE TABLE IF NOT EXISTS survey_investigation_teams (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        survey_batch_id INTEGER NOT NULL,
        commune_id INTEGER NOT NULL,
        team_number INTEGER NOT NULL,
        status VARCHAR(20) NOT NULL DEFAULT 'DRAFT',
        generation_code VARCHAR(60) NOT NULL,
        created_by_user_id INTEGER NULL,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        UNIQUE(survey_batch_id, team_number),
        FOREIGN KEY(survey_batch_id) REFERENCES survey_batches(id),
        FOREIGN KEY(commune_id) REFERENCES communes(id),
        FOREIGN KEY(created_by_user_id) REFERENCES users(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS survey_investigation_team_members (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        team_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        school_id INTEGER NOT NULL,
        level_code VARCHAR(20) NOT NULL,
        order_number INTEGER NOT NULL,
        created_at DATETIME NOT NULL,
        UNIQUE(team_id, user_id),
        UNIQUE(team_id, level_code),
        FOREIGN KEY(team_id) REFERENCES survey_investigation_teams(id)
            ON DELETE CASCADE,
        FOREIGN KEY(user_id) REFERENCES users(id),
        FOREIGN KEY(school_id) REFERENCES schools(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS survey_investigation_team_forms (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        team_id INTEGER NOT NULL,
        survey_form_id INTEGER NOT NULL,
        assignment_order INTEGER NOT NULL,
        created_at DATETIME NOT NULL,
        UNIQUE(survey_form_id),
        UNIQUE(team_id, assignment_order),
        FOREIGN KEY(team_id) REFERENCES survey_investigation_teams(id)
            ON DELETE CASCADE,
        FOREIGN KEY(survey_form_id) REFERENCES survey_forms(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS survey_team_generation_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        survey_batch_id INTEGER NOT NULL,
        commune_id INTEGER NOT NULL,
        generation_code VARCHAR(60) NOT NULL,
        action VARCHAR(30) NOT NULL,
        team_count INTEGER NOT NULL DEFAULT 0,
        household_count INTEGER NOT NULL DEFAULT 0,
        mn_count INTEGER NOT NULL DEFAULT 0,
        th_count INTEGER NOT NULL DEFAULT 0,
        thcs_count INTEGER NOT NULL DEFAULT 0,
        reserve_count INTEGER NOT NULL DEFAULT 0,
        actor_user_id INTEGER NULL,
        actor_name_snapshot VARCHAR(200) NULL,
        notes TEXT NULL,
        created_at DATETIME NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_survey_investigation_teams_batch
    ON survey_investigation_teams(survey_batch_id, status)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_survey_investigation_team_members_team
    ON survey_investigation_team_members(team_id, level_code)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_survey_investigation_team_forms_team
    ON survey_investigation_team_forms(team_id, assignment_order)
    """,
]


def read_text(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(f"Không tìm thấy tệp: {path}")
    return path.read_text(encoding="utf-8-sig")


def database_path() -> Path:
    sys.path.insert(0, str(PROJECT))
    old_cwd = Path.cwd()
    os.chdir(PROJECT)
    try:
        from app.database import DATABASE_PATH
        return Path(DATABASE_PATH)
    finally:
        os.chdir(old_cwd)
        try:
            sys.path.remove(str(PROJECT))
        except ValueError:
            pass


def backup_file(path: Path) -> None:
    if not path.exists():
        return
    dst = BACKUP / path.relative_to(PROJECT)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dst)


def restore_file(path: Path) -> None:
    src = BACKUP / path.relative_to(PROJECT)
    if src.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, path)
    elif path in {BUILDER_TPL, DETAIL_TPL} and path.exists():
        path.unlink()


def patch_router(text_value: str) -> str:
    if MARKER in text_value:
        return text_value

    required = [
        'router = APIRouter(',
        'def _sent_participants(' if 'def _sent_participants(' in text_value else 'def _participant_ids(',
        '@router.get("/danh-sach-truong"',
        'survey_investigation_participants',
        'survey_participant_submissions',
    ]
    for marker in required:
        if marker not in text_value:
            raise RuntimeError(
                f"survey_team_registration.py thiếu nền V1: {marker}"
            )

    return (
        text_value.rstrip()
        + "\n\n\n"
        + ROUTER_BLOCK.strip()
        + "\n"
    )


def patch_commune_template(text_value: str) -> str:
    if COMMUNE_BUTTON_MARKER in text_value:
        return text_value

    anchor = "<h2>Tình hình đăng ký của các trường</h2>"
    if anchor not in text_value:
        raise RuntimeError(
            "Không tìm thấy tiêu đề bảng tình hình đăng ký trường."
        )

    block = """
        <!-- === BAI_13B_10_V2_COMMUNE_BUTTON_START === -->
        <div style="display:flex;gap:10px;flex-wrap:wrap;margin:12px 0 16px">
            {% if batch %}
            <a
                class="button button-primary"
                href="/dieu-tra/phan-cong-to-dieu-tra/lap-to?batch_id={{ batch.id }}"
            >
                🎲 Lập tổ 3 cấp và chia hộ
            </a>
            {% endif %}
        </div>
        <!-- === BAI_13B_10_V2_COMMUNE_BUTTON_END === -->
"""
    return text_value.replace(
        anchor,
        anchor + "\n" + block,
        1,
    )


def patch_withdraw_lock(text_value: str) -> str:
    marker = "BAI_13B_10_V2_WITHDRAW_LOCK"
    if marker in text_value:
        return text_value

    anchor = """    participant_ids = _participant_ids(
        db,
        batch_id=batch_id,
        school_id=int(school["id"]),
    )
"""
    # Chỉ chọn occurrence trong hàm thu hồi: lấy occurrence cuối.
    pos = text_value.rfind(anchor)
    if pos < 0:
        raise RuntimeError(
            "Không tìm thấy điểm khóa Thu hồi danh sách ở route V1."
        )

    insert_at = pos
    block = """    # === BAI_13B_10_V2_WITHDRAW_LOCK_START ===
    # Khi xã/phường đã tạo dự thảo tổ, trường không được thu hồi danh sách
    # vì sẽ làm thay đổi cơ cấu 1 MN + 1 TH + 1 THCS.
    try:
        team_draft_exists = db.execute(
            text(
                "SELECT 1 FROM survey_investigation_teams "
                "WHERE survey_batch_id = :batch_id LIMIT 1"
            ),
            {"batch_id": int(batch_id)},
        ).scalar()
    except Exception:
        team_draft_exists = None

    if team_draft_exists is not None:
        return RedirectResponse(
            url=(
                "/dieu-tra/phan-cong-to-dieu-tra/giao-vien-tham-gia"
                f"?batch_id={batch_id}"
            ),
            status_code=303,
        )
    # === BAI_13B_10_V2_WITHDRAW_LOCK_END ===

"""
    return text_value[:insert_at] + block + text_value[insert_at:]


def migrate_db(db_path: Path) -> None:
    con = sqlite3.connect(str(db_path))
    try:
        con.execute("PRAGMA foreign_keys=ON")
        for statement in TEAM_SCHEMA_SQL:
            con.execute(statement)
        con.commit()
    finally:
        con.close()


def verify_db(db_path: Path) -> None:
    con = sqlite3.connect(str(db_path))
    try:
        names = {
            row[0]
            for row in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        for name in (
            "survey_investigation_teams",
            "survey_investigation_team_members",
            "survey_investigation_team_forms",
            "survey_team_generation_logs",
        ):
            if name not in names:
                raise RuntimeError(
                    f"Database chưa có bảng {name}."
                )
    finally:
        con.close()


def verify_source() -> None:
    router_text = read_text(ROUTER)
    commune_text = read_text(COMMUNE_TPL)

    for marker in (
        MARKER,
        '@router.get("/lap-to"',
        '@router.post("/lap-to/tao-ngau-nhien")',
        '@router.get(\n    "/lap-to/{team_id}"',
        "survey_investigation_team_members",
        "survey_investigation_team_forms",
        "BAI_13B_10_V2_WITHDRAW_LOCK",
    ):
        if marker not in router_text:
            raise RuntimeError(
                f"Kiểm tra router chưa đạt: {marker}"
            )

    if COMMUNE_BUTTON_MARKER not in commune_text:
        raise RuntimeError(
            "Trang xã chưa có nút Lập tổ 3 cấp."
        )

    subprocess.run(
        [sys.executable, "-m", "py_compile", str(ROUTER)],
        cwd=PROJECT,
        check=True,
    )

    from jinja2 import Environment, FileSystemLoader
    env = Environment(
        loader=FileSystemLoader(str(APP / "templates"))
    )
    env.get_template("survey_teams/commune_submissions.html")
    env.get_template("survey_teams/commune_team_builder.html")
    env.get_template("survey_teams/commune_team_detail.html")


def clear_cache() -> None:
    for cache in APP.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)


def main() -> int:
    print("=" * 112)
    print("BÀI 13B-10 V2 - GHÉP TỔ 3 CẤP NGẪU NHIÊN + CHIA ĐỀU HỘ DÂN")
    print("=" * 112)
    print("")
    print("V2 THỰC HIỆN:")
    print(" - Xã lấy CHỈ giáo viên có danh sách trường đã Gửi xã/phường.")
    print(" - Tạo mỗi tổ đúng 1 GV MN + 1 GV TH + 1 GV THCS.")
    print(" - Số tổ = cấp có ít GV nhất.")
    print(" - GV còn dư vào danh sách Dự phòng, không ghép sai cơ cấu.")
    print(" - Xáo trộn danh sách hộ và chia vòng tròn giữa các tổ.")
    print(" - Chênh lệch số hộ giữa các tổ tối đa 1.")
    print(" - Lưu DỰ THẢO cố định; mở lại trang không tự random lại.")
    print(" - Có Tạo lại ngẫu nhiên và Xóa dự thảo.")
    print(" - Có xem chi tiết hộ của từng tổ.")
    print("")
    print("V2 CHƯA GỬI PHÂN CÔNG XUỐNG TRƯỜNG/GIÁO VIÊN.")
    print("Bài V3 mới chốt và ghi vào survey_form_investigators.")
    print("")
    print("KHÔNG THAY ĐỔI dữ liệu hộ dân hoặc phân công cũ.")
    print("")

    for path in (ROUTER, COMMUNE_TPL):
        if not path.exists():
            raise RuntimeError(f"Không tìm thấy: {path}")

    db_path = database_path()

    BACKUP.mkdir(parents=True, exist_ok=False)
    for path in (
        ROUTER,
        COMMUNE_TPL,
        BUILDER_TPL,
        DETAIL_TPL,
    ):
        backup_file(path)

    db_backup = BACKUP / "database" / db_path.name
    db_backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(db_path, db_backup)

    try:
        router_text = read_text(ROUTER)
        router_text = patch_router(router_text)
        router_text = patch_withdraw_lock(router_text)
        ROUTER.write_text(
            router_text,
            encoding="utf-8",
        )

        COMMUNE_TPL.write_text(
            patch_commune_template(
                read_text(COMMUNE_TPL)
            ),
            encoding="utf-8",
        )

        BUILDER_TPL.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        BUILDER_TPL.write_text(
            BUILDER_TEMPLATE,
            encoding="utf-8",
        )
        DETAIL_TPL.write_text(
            DETAIL_TEMPLATE,
            encoding="utf-8",
        )

        migrate_db(db_path)
        verify_db(db_path)
        verify_source()
        clear_cache()

        print("")
        print("CAI DAT BAI 13B-10 V2 THANH CONG")
        print("Backup:", BACKUP)
        print("")
        print("KIỂM TRA:")
        print(" 1. Cho ít nhất 1 trường MN, 1 trường TH, 1 trường THCS")
        print("    gửi danh sách giáo viên về xã.")
        print(" 2. Tài khoản Xã -> 2.2.7 GV trường gửi về xã/phường.")
        print(" 3. Bấm 'Lập tổ 3 cấp và chia hộ'.")
        print(" 4. Bấm 'Tạo tổ ngẫu nhiên + chia hộ'.")
        print(" 5. Kiểm tra mỗi tổ đúng 3 cấp và số hộ chênh tối đa 1.")
        return 0

    except Exception:
        traceback.print_exc()
        print("")
        print("CÓ LỖI - ĐANG KHÔI PHỤC...")

        for path in (
            ROUTER,
            COMMUNE_TPL,
            BUILDER_TPL,
            DETAIL_TPL,
        ):
            restore_file(path)

        if db_backup.exists():
            shutil.copy2(
                db_backup,
                db_path,
            )

        clear_cache()
        print("ĐÃ KHÔI PHỤC SOURCE VÀ DATABASE VỀ TRƯỚC V2.")
        print("Backup:", BACKUP)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
