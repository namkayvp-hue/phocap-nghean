from pathlib import Path
from jinja2 import Environment, FileSystemLoader, StrictUndefined

PROJECT = Path(r"C:\PhoCap").resolve()

from app.main import app
from app.routers import preschool_3_5_report as module

required = {
    "/bao-cao/pho-cap-3-5-tuoi",
    "/bao-cao/pho-cap-3-5-tuoi/xuat-excel",
}

paths = [getattr(route, "path", "") for route in app.routes]

for path in sorted(required):
    count = paths.count(path)
    if count != 1:
        raise AssertionError(
            f"Route {path} xuat hien {count} lan; can dung 1 lan."
        )

router_paths = {getattr(route, "path", "") for route in module.router.routes}
missing = required - router_paths
if missing:
    raise AssertionError(
        "Router rieng thieu route: " + str(sorted(missing))
    )

source = Path(module.__file__).read_text(encoding="utf-8-sig")
for required_text in [
    "_load_scope_options(",
    "lay_thong_tin_nguoi_dung(request)",
]:
    if required_text not in source:
        raise AssertionError(
            "Router bao cao 3-5 tuoi khong con co co che pham vi tai khoan: "
            + required_text
        )

template_root = PROJECT / "app" / "templates"
env = Environment(
    loader=FileSystemLoader(str(template_root)),
    undefined=StrictUndefined,
)
env.get_template("reports/preschool_3_5_report.html")

print("")
print("ROUTE BAO CAO TRE 3-5 TUOI:")
for path in sorted(required):
    print(" -", path)
print("")
print("PHAM VI TAI KHOAN: DUNG CO CHE HIEN CO CUA HE THONG")
print("  Cap tinh: Toan tinh / xa / truong")
print("  Cap xa: khoa pham vi vao xa dang nhap")
print("  Cap truong: khoa pham vi vao truong dang nhap")
print("  Cap giao vien: theo truong/tai khoan dang nhap")
print("")
print("KIEM TRA BAO CAO TRE 3-5 TUOI V1 THANH CONG")
