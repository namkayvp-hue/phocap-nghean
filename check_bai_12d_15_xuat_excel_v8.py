from __future__ import annotations

from pathlib import Path
from typing import get_type_hints

from app.main import app as fastapi_app
from app.routers import student_survey_comparison as module

project = Path.cwd().resolve()
main_file = Path(__import__("app.main", fromlist=["x"]).__file__).resolve()
router_file = Path(module.__file__).resolve()

expected_main = (project / "app" / "main.py").resolve()
expected_router = (
    project / "app" / "routers" / "student_survey_comparison.py"
).resolve()

if main_file != expected_main:
    raise AssertionError(
        f"Nap nham app.main: {main_file}; can la {expected_main}"
    )

if router_file != expected_router:
    raise AssertionError(
        f"Nap nham router: {router_file}; can la {expected_router}"
    )

for function in (
    module.comparison_page,
    module.export_comparison_excel,
):
    hints = get_type_hints(function)
    if hints.get("school_id") is not str:
        raise AssertionError(
            f"school_id cua {function.__name__} chua nhan chuoi rong."
        )

required = {
    "/dieu-tra/{batch_id}/doi-chieu-hoc-sinh",
    "/dieu-tra/{batch_id}/doi-chieu-hoc-sinh/xuat-excel",
}

app_paths = [
    getattr(route, "path", "")
    for route in fastapi_app.routes
]

for path in required:
    count = app_paths.count(path)
    if count != 1:
        raise AssertionError(
            f"Route {path} xuat hien {count} lan; can dung 1 lan."
        )

openapi = fastapi_app.openapi()
for path in required:
    operation = openapi["paths"][path]["get"]
    school_parameters = [
        item
        for item in operation.get("parameters", [])
        if item.get("name") == "school_id"
        and item.get("in") == "query"
    ]
    if len(school_parameters) != 1:
        raise AssertionError(
            f"Khong tim thay tham so school_id cua route {path}."
        )
    schema = school_parameters[0].get("schema", {})
    if schema.get("type") != "string":
        raise AssertionError(
            f"school_id cua route {path} van khong phai chuoi: {schema}"
        )

if module._parse_optional_int("") is not None:
    raise AssertionError("Chuoi rong chua duoc doi thanh None.")
if module._parse_optional_int("  ") is not None:
    raise AssertionError("Chuoi trang chua duoc doi thanh None.")
if module._parse_optional_int("123") != 123:
    raise AssertionError("Ma truong hop le chua duoc doi thanh so nguyen.")
if module._parse_optional_int("abc") is not None:
    raise AssertionError("Ma truong khong hop le chua duoc bo qua an toan.")

print("")
print("APP MAIN DANG DUNG:", main_file)
print("ROUTER DANG DUNG:", router_file)
print("")
print("HAI ROUTE DA NHAN SCHOOL_ID RONG AN TOAN:")
for path in sorted(required):
    print(" -", path)
print("")
print("KIEM TRA SUA LOI XUAT EXCEL BAI 12D-15 V8 THANH CONG")
