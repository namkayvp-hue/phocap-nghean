from __future__ import annotations

import os
import shutil
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path


PROJECT = Path(r"C:\PhoCap").resolve()
TARGET = PROJECT / "app" / "routers" / "student_survey_comparison.py"
PYTHON = PROJECT / ".venv" / "Scripts" / "python.exe"
STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = (
    PROJECT
    / "exports"
    / f"backup_bai_12d_15_xuat_excel_v8_{STAMP}"
)
BACKUP_FILE = BACKUP / "app" / "routers" / TARGET.name
CHECK_FILE = PROJECT / "check_bai_12d_15_xuat_excel_v8.py"

OLD_PARAMETER = "    school_id: int | None = None,"
NEW_PARAMETER = '    school_id: str = "",'
PARSE_LINE = "    school_id = _parse_optional_int(school_id)"
RESULT_GROUP_LINE = "    result_group = result_group.strip().upper()"

HELPER = '''\n\ndef _parse_optional_int(value: Any) -> int | None:\n    text = str(value or "").strip()\n    if not text:\n        return None\n    try:\n        return int(text)\n    except (TypeError, ValueError):\n        return None\n'''

CHECK_CODE = r'''from __future__ import annotations

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
'''


def copy_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def restore() -> None:
    if BACKUP_FILE.exists():
        copy_file(BACKUP_FILE, TARGET)
        print("")
        print("DA KHOI PHUC TEP ROUTER CU.")


def patch_source(text: str) -> str:
    old_count = text.count(OLD_PARAMETER)
    new_count = text.count(NEW_PARAMETER)

    if old_count == 2:
        text = text.replace(OLD_PARAMETER, NEW_PARAMETER)
    elif old_count == 0 and new_count == 2:
        pass
    else:
        raise RuntimeError(
            "Khong nhan dien dung 2 khai bao school_id trong router. "
            f"So khai bao cu: {old_count}; so khai bao moi: {new_count}."
        )

    if "def _parse_optional_int(" not in text:
        anchor = "\ndef _school_name("
        if text.count(anchor) != 1:
            raise RuntimeError(
                "Khong tim thay vi tri chen ham xu ly school_id rong."
            )
        text = text.replace(
            anchor,
            HELPER + anchor,
            1,
        )

    parse_count = text.count(PARSE_LINE)
    if parse_count == 0:
        result_count = text.count(RESULT_GROUP_LINE)
        if result_count != 2:
            raise RuntimeError(
                "Khong nhan dien dung 2 vi tri xu ly bo loc. "
                f"Tim thay: {result_count}."
            )
        text = text.replace(
            RESULT_GROUP_LINE,
            PARSE_LINE + "\n\n" + RESULT_GROUP_LINE,
        )
    elif parse_count != 2:
        raise RuntimeError(
            "So dong chuyen school_id khong hop le: "
            f"{parse_count}; can dung 2."
        )

    if text.count(NEW_PARAMETER) != 2:
        raise RuntimeError("Chua doi du 2 tham so school_id sang chuoi.")
    if text.count(PARSE_LINE) != 2:
        raise RuntimeError("Chua them du 2 dong xu ly school_id rong.")

    return text


def clear_python_cache() -> None:
    app_dir = PROJECT / "app"
    for cache in app_dir.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)


def run_checks() -> None:
    subprocess.run(
        [
            str(PYTHON),
            "-m",
            "py_compile",
            str(TARGET),
            str(PROJECT / "app" / "main.py"),
        ],
        cwd=PROJECT,
        check=True,
    )

    CHECK_FILE.write_text(CHECK_CODE, encoding="utf-8")

    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(PROJECT)

    subprocess.run(
        [str(PYTHON), str(CHECK_FILE)],
        cwd=PROJECT,
        env=environment,
        check=True,
    )


try:
    print("")
    print("=" * 62)
    print("SUA LOI XUAT EXCEL BAI 12D-15 V8")
    print("CHO PHEP SCHOOL_ID RONG KHI KHONG CHON TRUONG")
    print("=" * 62)

    if not PROJECT.exists():
        raise FileNotFoundError(f"Khong tim thay du an: {PROJECT}")
    if not TARGET.exists():
        raise FileNotFoundError(f"Khong tim thay router: {TARGET}")
    if not PYTHON.exists():
        raise FileNotFoundError(f"Khong tim thay Python: {PYTHON}")

    print("")
    print("BUOC 1 - SAO LUU TEP ROUTER HIEN TAI")
    BACKUP.mkdir(parents=True, exist_ok=False)
    copy_file(TARGET, BACKUP_FILE)
    print("Ban sao an toan:", BACKUP)

    print("")
    print("BUOC 2 - SUA THAM SO SCHOOL_ID RONG")
    original = TARGET.read_text(encoding="utf-8-sig")
    patched = patch_source(original)
    TARGET.write_text(patched, encoding="utf-8")
    print("Da cap nhat:", TARGET)

    print("")
    print("BUOC 3 - XOA BO NHO DEM PYTHON")
    clear_python_cache()

    print("")
    print("BUOC 4 - KIEM TRA CU PHAP, ROUTE VA OPENAPI")
    run_checks()

    print("")
    print("=" * 62)
    print("SUA LOI XUAT EXCEL BAI 12D-15 V8 THANH CONG")
    print("=" * 62)
    print("Ban sao an toan:", BACKUP)

except Exception as exc:
    print("")
    print("SUA LOI KHONG THANH CONG:")
    print(exc)
    traceback.print_exc()
    restore()
    print("Ban sao an toan:", BACKUP)
    sys.exit(1)
