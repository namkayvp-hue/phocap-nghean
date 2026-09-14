from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def _clean(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _school_year_start(value: Any) -> int | None:
    """Return the first year from a school-year label such as 2025-2026."""
    match = re.search(r"(\d{4})\D+(\d{4})", _clean(value))
    if not match:
        return None
    first = int(match.group(1))
    second = int(match.group(2))
    if second != first + 1:
        return None
    return first


def _table_exists(db: Session, table_name: str) -> bool:
    row = db.execute(
        text(
            "SELECT 1 FROM sqlite_master "
            "WHERE type='table' AND name=:name LIMIT 1"
        ),
        {"name": table_name},
    ).first()
    return row is not None


def _target_year_start(db: Session, school_year_id: int) -> int | None:
    row = db.execute(
        text(
            "SELECT code,name FROM school_years "
            "WHERE id=:year_id LIMIT 1"
        ),
        {"year_id": int(school_year_id)},
    ).mappings().first()
    if row is None:
        return None
    return _school_year_start(row.get("code") or row.get("name"))


def _history_rows(db: Session, school_id: int) -> list[dict[str, Any]]:
    if not _table_exists(db, "school_name_histories"):
        return []
    rows = db.execute(
        text(
            """
            SELECT h.id,
                   h.school_id,
                   h.effective_school_year_id,
                   h.old_name,
                   h.new_name,
                   y.code AS year_code,
                   y.name AS year_name
            FROM school_name_histories h
            JOIN school_years y ON y.id=h.effective_school_year_id
            WHERE h.school_id=:school_id
            ORDER BY h.id ASC
            """
        ),
        {"school_id": int(school_id)},
    ).mappings().all()
    return [dict(row) for row in rows]


def school_name_for_year(
    db: Session,
    *,
    school_id: int,
    current_name: str,
    school_year_id: int | None,
) -> str:
    """
    Resolve the school's name for one school year.

    Rules:
    - no selected year/history -> current schools.name;
    - before the first rename -> old_name of the first future rename;
    - from a rename's effective year until the next rename -> new_name of the
      latest rename whose effective year is not after the selected year.

    School-year ordering intentionally uses the year code/name, not row id or
    start_date, because ids are not chronological and old data can contain
    imperfect start/end dates.
    """
    fallback = _clean(current_name)
    if school_year_id is None:
        return fallback

    target_start = _target_year_start(db, int(school_year_id))
    if target_start is None:
        return fallback

    resolved_rows: list[tuple[int, int, dict[str, Any]]] = []
    for row in _history_rows(db, int(school_id)):
        effective_start = _school_year_start(row.get("year_code") or row.get("year_name"))
        if effective_start is None:
            continue
        resolved_rows.append((effective_start, int(row.get("id") or 0), row))

    if not resolved_rows:
        return fallback

    resolved_rows.sort(key=lambda item: (item[0], item[1]))

    past_or_current = [item for item in resolved_rows if item[0] <= target_start]
    if past_or_current:
        row = past_or_current[-1][2]
        return _clean(row.get("new_name")) or fallback

    first_future = resolved_rows[0][2]
    return _clean(first_future.get("old_name")) or fallback


def school_names_for_year(
    db: Session,
    *,
    schools: Iterable[Any],
    school_year_id: int | None,
) -> dict[int, str]:
    """Resolve historical names for a collection of School-like objects."""
    result: dict[int, str] = {}
    for school in schools:
        school_id = int(getattr(school, "id"))
        current_name = str(getattr(school, "name", "") or "")
        result[school_id] = school_name_for_year(
            db,
            school_id=school_id,
            current_name=current_name,
            school_year_id=school_year_id,
        )
    return result
