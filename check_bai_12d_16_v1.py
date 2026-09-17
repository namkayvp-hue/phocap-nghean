from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

PROJECT = Path.cwd().resolve()
sys.path.insert(0, str(PROJECT))

from app.main import app as fastapi_app, templates
from app.routers.student_survey_comparison import router as comparison_router

required_routes = {
    ("GET", "/dieu-tra/{batch_id}/doi-chieu-hoc-sinh"),
    ("GET", "/dieu-tra/{batch_id}/doi-chieu-hoc-sinh/xuat-excel"),
    (
        "GET",
        "/dieu-tra/{batch_id}/doi-chieu-hoc-sinh/"
        "xu-ly/doi-tuong/{person_id}",
    ),
    (
        "POST",
        "/dieu-tra/{batch_id}/doi-chieu-hoc-sinh/"
        "xu-ly/doi-tuong/{person_id}/lien-ket",
    ),
    (
        "POST",
        "/dieu-tra/{batch_id}/doi-chieu-hoc-sinh/"
        "xu-ly/doi-tuong/{person_id}/ghi-nhan",
    ),
    (
        "POST",
        "/dieu-tra/{batch_id}/doi-chieu-hoc-sinh/"
        "xu-ly/doi-tuong/{person_id}/bo-lien-ket",
    ),
    (
        "GET",
        "/dieu-tra/{batch_id}/doi-chieu-hoc-sinh/"
        "xu-ly/hoc-sinh/{student_id}",
    ),
    (
        "POST",
        "/dieu-tra/{batch_id}/doi-chieu-hoc-sinh/"
        "xu-ly/hoc-sinh/{student_id}/lien-ket",
    ),
    (
        "POST",
        "/dieu-tra/{batch_id}/doi-chieu-hoc-sinh/"
        "xu-ly/hoc-sinh/{student_id}/ghi-nhan",
    ),
}

router_routes = set()
for route in comparison_router.routes:
    path = getattr(route, "path", "")
    for method in getattr(route, "methods", set()) or set():
        router_routes.add((method, path))

app_routes = []
for route in fastapi_app.routes:
    path = getattr(route, "path", "")
    for method in getattr(route, "methods", set()) or set():
        app_routes.append((method, path))

missing_router = required_routes - router_routes
missing_app = required_routes - set(app_routes)
if missing_router:
    raise AssertionError(
        f"Router doi chieu thieu route: {sorted(missing_router)}"
    )
if missing_app:
    raise AssertionError(
        f"FastAPI app thieu route: {sorted(missing_app)}"
    )

for route_key in required_routes:
    count = app_routes.count(route_key)
    if count != 1:
        raise AssertionError(
            f"Route {route_key} xuat hien {count} lan; can dung 1 lan."
        )

templates.env.get_template("surveys/student_survey_comparison.html")
templates.env.get_template("surveys/student_survey_resolution.html")

model_path = PROJECT / "app" / "comparison_models.py"
if not model_path.exists():
    raise AssertionError("Thieu app/comparison_models.py")

database = PROJECT / "data" / "phocap.db"
connection = sqlite3.connect(database)
try:
    table = connection.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
          AND name = 'student_survey_resolution_logs'
        """
    ).fetchone()
    if table is None:
        raise AssertionError(
            "Chua tao bang student_survey_resolution_logs"
        )

    columns = {
        row[1]
        for row in connection.execute(
            "PRAGMA table_info(student_survey_resolution_logs)"
        )
    }
    required_columns = {
        "id",
        "survey_batch_id",
        "survey_person_id",
        "student_id",
        "previous_student_id",
        "action_code",
        "result_before",
        "note",
        "actor_user_id",
        "created_at",
    }
    missing_columns = required_columns - columns
    if missing_columns:
        raise AssertionError(
            f"Bang nhat ky thieu cot: {sorted(missing_columns)}"
        )
finally:
    connection.close()

print("ROUTE BAI 12D-16:")
for method, path in sorted(required_routes, key=lambda item: item[1]):
    print(f" - {method:4} {path}")
print("KIEM TRA BAI 12D-16 V1 THANH CONG")
