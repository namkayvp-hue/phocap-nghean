from __future__ import annotations

import importlib
import sys
from pathlib import Path

from sqlalchemy import inspect


PROJECT = Path.cwd().resolve()
sys.path.insert(0, str(PROJECT))

main_module = importlib.import_module("app.main")
comparison_module = importlib.import_module(
    "app.routers.student_survey_comparison"
)
models_module = importlib.import_module("app.comparison_models")
database_module = importlib.import_module("app.database")

expected_router = (
    PROJECT / "app" / "routers" / "student_survey_comparison.py"
).resolve()
actual_router = Path(comparison_module.__file__).resolve()
if actual_router != expected_router:
    raise AssertionError(
        f"Python nap nham router: {actual_router}; can la {expected_router}"
    )

required_routes = {
    ("GET", "/dieu-tra/{batch_id}/doi-chieu-hoc-sinh/chot-ket-qua"),
    ("POST", "/dieu-tra/{batch_id}/doi-chieu-hoc-sinh/chot-ket-qua/chot"),
    ("POST", "/dieu-tra/{batch_id}/doi-chieu-hoc-sinh/chot-ket-qua/mo-lai"),
    ("GET", "/dieu-tra/{batch_id}/doi-chieu-hoc-sinh/chot-ket-qua/xuat-bien-ban"),
}

actual_routes: set[tuple[str, str]] = set()
for route in main_module.app.routes:
    path = getattr(route, "path", "")
    for method in getattr(route, "methods", set()) or set():
        actual_routes.add((method, path))

missing_routes = required_routes - actual_routes
if missing_routes:
    raise AssertionError(
        "Thieu route BAI 12D-17: "
        + ", ".join(f"{method} {path}" for method, path in sorted(missing_routes))
    )

for method, path in required_routes:
    count = sum(
        1
        for route in main_module.app.routes
        if getattr(route, "path", "") == path
        and method in (getattr(route, "methods", set()) or set())
    )
    if count != 1:
        raise AssertionError(
            f"Route {method} {path} xuat hien {count} lan; can dung 1 lan."
        )

main_module.templates.env.get_template(
    "surveys/student_survey_comparison.html"
)
main_module.templates.env.get_template(
    "surveys/student_survey_signoff.html"
)

model = getattr(
    models_module,
    "StudentSurveyComparisonSignoff",
    None,
)
if model is None:
    raise AssertionError("Thieu model StudentSurveyComparisonSignoff.")

TABLE_NAME = "student_survey_comparison_signoffs"
tables = set(inspect(database_module.engine).get_table_names())
if TABLE_NAME not in tables:
    raise AssertionError(f"Chua co bang {TABLE_NAME}.")

router_text = expected_router.read_text(encoding="utf-8")
for marker in (
    "BÀI 12D-17 - CHỐT KẾT QUẢ ĐỐI CHIẾU",
    "def comparison_signoff_page",
    "def sign_comparison_result",
    "def reopen_comparison_result",
    "def export_comparison_signoff_minutes",
    "signoff_locked",
):
    if marker not in router_text:
        raise AssertionError(f"Thieu noi dung kiem tra: {marker}")

print("ROUTE BAI 12D-17:")
for method, path in sorted(required_routes):
    print(f" - {method} {path}")
print(f"BANG DU LIEU: {TABLE_NAME}")
print("KIEM TRA BAI 12D-17 V1 THANH CONG")
