from __future__ import annotations

from pathlib import Path

PROJECT = Path(r"C:\PhoCap").resolve()

from app.main import app
from app.routers.preschool_3_5_report import (
    router as preschool_3_5_report_router,
)

required = {
    "/bao-cao/pho-cap-3-5-tuoi",
    "/bao-cao/pho-cap-3-5-tuoi/xuat-excel",
}

app_paths = [
    getattr(route, "path", "")
    for route in app.routes
]

router_paths = [
    getattr(route, "path", "")
    for route in preschool_3_5_report_router.routes
]

print("")
print("ROUTE TRONG ROUTER RIENG:")
for path in sorted(set(router_paths)):
    if "pho-cap-3-5-tuoi" in path:
        print(" -", path)

print("")
print("ROUTE TRONG FASTAPI APP:")
for path in sorted(set(app_paths)):
    if "pho-cap-3-5-tuoi" in path:
        print(" -", path)

for path in sorted(required):
    router_count = router_paths.count(path)
    app_count = app_paths.count(path)

    if router_count != 1:
        raise AssertionError(
            f"Router rieng: {path} xuat hien {router_count} lan; can 1."
        )

    if app_count != 1:
        raise AssertionError(
            f"FastAPI app: {path} xuat hien {app_count} lan; can 1."
        )

router_file = PROJECT / "app" / "routers" / "preschool_3_5_report.py"
source = router_file.read_text(encoding="utf-8-sig")

for required_text in [
    "_load_scope_options(",
    "lay_thong_tin_nguoi_dung(request)",
]:
    if required_text not in source:
        raise AssertionError(
            "Co che pham vi/quyen cua bao cao 3-5 tuoi khong con day du: "
            + required_text
        )

template = (
    PROJECT
    / "app"
    / "templates"
    / "reports"
    / "preschool_3_5_report.html"
)

if not template.exists():
    raise AssertionError("Thieu giao dien preschool_3_5_report.html.")

print("")
print("PHAM VI:")
print(" - Cap tinh: theo quyen cap tinh hien co")
print(" - Cap xa: theo xa cua tai khoan")
print(" - Cap truong: theo truong cua tai khoan")
print(" - Cap giao vien: theo truong/phan quyen hien co")
print("")
print("KIEM TRA BAO CAO TRE 3-5 TUOI V2 THANH CONG")
