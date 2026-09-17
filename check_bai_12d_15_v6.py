from __future__ import annotations

import sys
from pathlib import Path

PROJECT = Path.cwd().resolve()
sys.path.insert(0, str(PROJECT))

import app
from app.main import app as fastapi_app, templates
from app.routers.student_survey_comparison import (
    router as comparison_router,
)

expected_app = (PROJECT / "app" / "__init__.py").resolve()
actual_app = Path(app.__file__).resolve()
if actual_app != expected_app:
    raise AssertionError(
        f"Python nap nham goi app: {actual_app}; can la {expected_app}"
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

print("APP DANG DUNG:", actual_app)
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
print("KIEM TRA BAI 12D-15 V6 THANH CONG")
