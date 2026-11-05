"""Read-only progress of the teams actually assigned to a survey batch."""
from typing import Any

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.permissions import is_province_reader, normalize_role_code


def build_team_progress(
    *, db: Session, batch_id: int, commune_id: int,
    user: dict[str, Any], status_codes,
) -> list[dict[str, Any]]:
    role = normalize_role_code(user.get("role_code"))
    params = {"batch_id": int(batch_id), "commune_id": int(commune_id)}
    scope = "t.survey_batch_id=:batch_id AND t.commune_id=:commune_id AND t.status='SENT'"
    if role == "XA":
        if user.get("commune_id") is None or int(user["commune_id"]) != int(commune_id):
            return []
    elif role in {"TRUONG", "GIAO_VIEN"}:
        # These progress reports already use school-wide scope for both roles.
        if user.get("school_id") is None:
            return []
        params["school_id"] = int(user["school_id"])
        scope += " AND EXISTS (SELECT 1 FROM survey_investigation_team_members sm WHERE sm.team_id=t.id AND sm.school_id=:school_id)"
    elif not is_province_reader(role):
        return []

    inspector = inspect(db.connection())
    if not all(inspector.has_table(name) for name in (
        "survey_investigation_teams", "survey_investigation_team_members",
        "survey_investigation_team_forms",
    )):
        return []

    teams = {}
    for row in db.execute(text(f"""
        SELECT t.id, t.team_number FROM survey_investigation_teams t
        WHERE {scope} ORDER BY t.team_number, t.id
    """), params).mappings():
        teams[row["id"]] = {
            "team_id": row["id"], "team_number": row["team_number"],
            "members": [], "hamlets": set(), "counts": {code: 0 for code in status_codes},
        }
    if not teams:
        return []

    for row in db.execute(text(f"""
        SELECT tm.team_id, tm.user_id, tm.level_code, u.full_name, u.username,
               s.name AS school_name
        FROM survey_investigation_team_members tm
        JOIN survey_investigation_teams t ON t.id=tm.team_id
        JOIN users u ON u.id=tm.user_id
        LEFT JOIN schools s ON s.id=tm.school_id
        WHERE {scope} ORDER BY tm.team_id, tm.order_number, tm.user_id
    """), params).mappings():
        teams[row["team_id"]]["members"].append(dict(row))

    # Aggregate forms separately from members: three members must not triple
    # the denominator, and the last editor/primary investigator is irrelevant.
    for row in db.execute(text(f"""
        SELECT tf.team_id, sf.status, h.hamlet_name, COUNT(DISTINCT sf.id) AS n
        FROM survey_investigation_team_forms tf
        JOIN survey_investigation_teams t ON t.id=tf.team_id
        JOIN survey_forms sf ON sf.id=tf.survey_form_id AND sf.survey_batch_id=t.survey_batch_id
        JOIN households h ON h.id=sf.household_id
        WHERE {scope} GROUP BY tf.team_id, sf.status, h.hamlet_name
    """), params).mappings():
        team = teams[row["team_id"]]
        team["counts"][row["status"]] = team["counts"].get(row["status"], 0) + int(row["n"])
        team["hamlets"].add(row["hamlet_name"] or "Chưa xác định thôn/xóm")

    for team in teams.values():
        team["hamlets"] = sorted(team["hamlets"])
        team["total"] = sum(team["counts"].values())
        team["progress_percent"] = (
            round(team["counts"].get("DA_HOAN_THANH", 0) * 100 / team["total"])
            if team["total"] else 0
        )
    return list(teams.values())
