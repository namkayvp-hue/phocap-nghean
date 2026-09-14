from __future__ import annotations

import sys
from pathlib import Path

PROJECT = Path.cwd().resolve()
sys.path.insert(0, str(PROJECT))

import importlib

main_module = importlib.import_module("app.main")
comparison_module = importlib.import_module(
    "app.routers.student_survey_comparison"
)

fastapi_app = main_module.app
templates = main_module.templates
comparison_router = comparison_module.router

expected_main = (PROJECT / "app" / "main.py").resolve()
actual_main = Path(main_module.__file__).resolve()
if actual_main != expected_main:
    raise AssertionError(
        f"Python nap nham app.main: {actual_main}; can la {expected_main}"
    )

expected_router = (
    PROJECT / "app" / "routers" / "student_survey_comparison.py"
).resolve()
actual_router = Path(comparison_module.__file__).resolve()
if actual_router != expected_router:
    raise AssertionError(
        "Python nap nham router doi chieu: "
        f"{actual_router}; can la {expected_router}"
    )

required = {
    "/dieu-tra/{batch_id}/doi-chieu-hoc-sinh",
    "/dieu-tra/{batch_id}/doi-chieu-hoc-sinh/xuat-excel",
}

child_paths = {
    getattr(route, "path", "")
    for route in comparison_router.routes
}
app_paths = [
    getattr(route, "path", "")
    for route in fastapi_app.routes
]

print("APP MAIN DANG DUNG:", actual_main)
print("ROUTER DANG DUNG:", actual_router)
print("ROUTE TRONG ROUTER DOI CHIEU:")
for path in sorted(path for path in child_paths if "doi-chieu-hoc-sinh" in path):
    print(" -", path)
print("ROUTE TRONG FASTAPI APP:")
for path in sorted(path for path in app_paths if "doi-chieu-hoc-sinh" in path):
    print(" -", path)

missing_child = required - child_paths
missing_app = required - set(app_paths)
if missing_child:
    raise AssertionError(f"Router doi chieu thieu: {sorted(missing_child)}")
if missing_app:
    raise AssertionError(f"FastAPI app thieu: {sorted(missing_app)}")
for path in required:
    count = app_paths.count(path)
    if count != 1:
        raise AssertionError(
            f"Route {path} xuat hien {count} lan; can dung 1 lan"
        )

templates.env.get_template("surveys/student_survey_comparison.html")
print("KIEM TRA BAI 12D-15 V7 THANH CONG")
