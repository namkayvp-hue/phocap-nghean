"""Read completed merger history for the existing school rename screen."""
import json
import sqlite3
from typing import Any

from app.services.school_merger_service import _year_start_value


def _json(value, expected_type):
    try:
        result = json.loads(value or "null")
    except (ValueError, TypeError):
        return expected_type()
    return result if isinstance(result, expected_type) else expected_type()


def school_rename_lineage(
    con: sqlite3.Connection, *, schools: list[dict[str, Any]], school_year_id: int,
) -> list[dict[str, Any]]:
    if not schools:
        return []
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    school_map = {r["id"]: dict(r) for r in con.execute("""
        SELECT s.id,s.code,s.name,c.name AS commune_name
        FROM schools s LEFT JOIN communes c ON c.id=s.commune_id
    """)}
    years = {r["id"]: dict(r) for r in con.execute("SELECT id,code,name FROM school_years")}
    selected_start = _year_start_value(years.get(school_year_id, {}))
    histories = {}
    if "school_name_histories" in tables:
        for row in con.execute("SELECT school_id,old_name,new_name,changed_at FROM school_name_histories ORDER BY changed_at,id"):
            histories.setdefault(row["school_id"], []).append(dict(row))

    def name_at(school_id, when):
        # The first later rename retains the name in use at the merger date.
        for history in histories.get(school_id, []):
            if history["changed_at"] >= when:
                return history["old_name"]
        return school_map.get(school_id, {}).get("name", f"Trường ID {school_id}")

    operations = {}
    if "school_merger_operations" in tables:
        for row in con.execute("SELECT * FROM school_merger_operations ORDER BY created_at,id"):
            op = dict(row)
            start = _year_start_value(years.get(op["school_year_id"], {}))
            if op["school_year_id"] != school_year_id and (
                selected_start is None or start is None or start > selected_start
            ):
                continue
            source_ids = _json(op["source_school_ids_json"], list)
            op["sources"] = [int(x) for x in source_ids if str(x).isdigit() and int(x) != op["target_school_id"]]
            if not op["sources"]:
                continue  # Rename-only/survivor operations are not mergers.
            op["summary"] = _json(op["summary_json"], dict)
            operations.setdefault(op["target_school_id"], []).append(op)

    rows = []
    for school in schools:
        sid = int(school["id"])
        relevant = operations.get(sid, [])
        before = {}

        def collect(target_id, cutoff=None, visiting=None):
            visiting = set(visiting or ())
            if target_id in visiting:
                return
            visiting.add(target_id)
            for op in operations.get(target_id, []):
                if cutoff is not None and (op["created_at"], op["id"]) >= cutoff:
                    continue
                summary = op["summary"]
                old_target = summary.get("target_school_old_name") or summary.get("target_school_name") or name_at(target_id, op["created_at"])
                before.setdefault(target_id, {**school_map.get(target_id, {"id": target_id}), "name": old_target})
                snapshots = summary.get("source_school_names")
                if not isinstance(snapshots, list):
                    snapshots = [summary["source_school_name"]] if summary.get("source_school_name") and len(op["sources"]) == 1 else []
                for index, source_id in enumerate(op["sources"]):
                    source_name = snapshots[index] if len(snapshots) == len(op["sources"]) else name_at(source_id, op["created_at"])
                    before.setdefault(source_id, {**school_map.get(source_id, {"id": source_id}), "name": source_name})
                    collect(source_id, (op["created_at"], op["id"]), visiting)

        collect(sid)
        last = relevant[-1] if relevant else None
        merged_name = (last["summary"].get("target_school_name") or name_at(sid, last["created_at"])) if last else school["name"]
        rows.append({
            "school_id": sid, "school_code": school.get("code") or "",
            "current_name": school["name"], "merged_name": merged_name,
            "has_merger": bool(last), "before_schools": list(before.values()),
            "merger_year": (years.get(last["school_year_id"], {}).get("code") or "") if last else "",
        })
    return rows
