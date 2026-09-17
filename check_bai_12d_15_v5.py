
from pathlib import Path

import app

from app.main import (
    app as fastapi_app,
    templates,
)

from app.routers.student_survey_comparison import (
    router as child_router,
)


project = Path.cwd().resolve()

expected_app = (
    project
    / "app"
    / "__init__.py"
).resolve()

actual_app = Path(
    app.__file__
).resolve()

if actual_app != expected_app:
    raise AssertionError(
        "Nap nham app: "
        f"{actual_app}; "
        f"can la {expected_app}"
    )


required = {
    (
        "/dieu-tra/{batch_id}"
        "/doi-chieu-hoc-sinh"
    ),
    (
        "/dieu-tra/{batch_id}"
        "/doi-chieu-hoc-sinh"
        "/xuat-excel"
    ),
}


app_paths = [
    getattr(
        route,
        "path",
        "",
    )
    for route in fastapi_app.routes
]


missing = (
    required
    - set(app_paths)
)

if missing:
    raise AssertionError(
        "FastAPI app thieu route: "
        f"{sorted(missing)}"
    )


for path in sorted(required):
    count = app_paths.count(path)

    if count != 1:
        raise AssertionError(
            f"Route {path} "
            f"xuat hien {count} lan; "
            "can dung 1 lan"
        )


child_paths = {
    getattr(
        route,
        "path",
        "",
    )
    for route in child_router.routes
}


expected_child = {
    (
        "/{batch_id}"
        "/doi-chieu-hoc-sinh"
    ),
    (
        "/{batch_id}"
        "/doi-chieu-hoc-sinh"
        "/xuat-excel"
    ),
}


if not expected_child.issubset(
    child_paths
):
    raise AssertionError(
        "Router con khong dung: "
        f"{sorted(child_paths)}"
    )


templates.env.get_template(
    "surveys/"
    "student_survey_comparison.html"
)


print(
    "APP DANG DUNG:",
    actual_app,
)

print(
    "ROUTE DA NAP:"
)

for path in sorted(required):
    print(
        " -",
        path,
    )

print(
    "KIEM TRA BAI 12D-15 "
    "V4 THANH CONG"
)
