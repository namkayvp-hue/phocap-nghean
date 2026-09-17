from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path


PROJECT = Path(os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")).resolve()
PACKAGE = Path(
    os.environ.get(
        "PHOCAP_PACKAGE",
        r"C:\PhoCap\exports\Bai_12D_15_V2_Doi_chieu_du_lieu_hoc_sinh",
    )
).resolve()
SOURCE = PACKAGE / "tep_thay_the"
PYTHON = Path(sys.executable).resolve()
STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = PROJECT / "exports" / f"backup_bai_12d_15_v7_{STAMP}"

FILES_TO_BACKUP = [
    Path("app/main.py"),
    Path("app/routers/student_survey_comparison.py"),
    Path("app/templates/surveys/student_survey_comparison.html"),
    Path("app/templates/surveys/summary_report.html"),
    Path("app/templates/surveys/households.html"),
]

FILES_TO_COPY = [
    Path("app/routers/student_survey_comparison.py"),
    Path("app/templates/surveys/student_survey_comparison.html"),
    Path("app/templates/surveys/summary_report.html"),
    Path("app/templates/surveys/households.html"),
]

IMPORT_LINE = (
    "from app.routers.student_survey_comparison "
    "import router as student_survey_comparison_router"
)
IMPORT_ANCHOR = "from app.routers.users import router as users_router"

REGISTER_START = "# === BAI 12D-15 V7: BAT DAU ==="
REGISTER_END = "# === BAI 12D-15 V7: KET THUC ==="
REGISTER_BLOCK = f'''\n{REGISTER_START}
# Dang ky truc tiep cac APIRoute da co day du prefix /dieu-tra.
# Cach nay tranh phu thuoc vao thu tu include_router cua cac router cha/con.
for _student_survey_route in student_survey_comparison_router.routes:
    _route_exists = any(
        getattr(_existing_route, "path", None)
        == getattr(_student_survey_route, "path", None)
        and getattr(_existing_route, "methods", None)
        == getattr(_student_survey_route, "methods", None)
        for _existing_route in app.router.routes
    )
    if not _route_exists:
        app.router.routes.append(_student_survey_route)
{REGISTER_END}
'''
REGISTER_ANCHOR = "app.include_router(historical_data_router)"


def copy_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def restore_backup() -> None:
    print("\nDANG KHOI PHUC MA NGUON CU...")
    for relative in FILES_TO_BACKUP:
        saved = BACKUP / relative
        current = PROJECT / relative
        if saved.exists():
            copy_file(saved, current)
        elif current.exists():
            current.unlink()
    print("DA KHOI PHUC MA NGUON CU.")


def clean_old_attempts(main_text: str) -> str:
    # Xoa khoi V7 cu neu chay lai.
    main_text = re.sub(
        re.escape(REGISTER_START)
        + r".*?"
        + re.escape(REGISTER_END)
        + r"\s*",
        "",
        main_text,
        flags=re.DOTALL,
    )

    # Xoa cac dong dang ky truc tiep cu de tranh trung lap.
    main_text = re.sub(
        r"(?m)^from app\.routers\.student_survey_comparison "
        r"import router as student_survey_comparison_router\s*\n",
        "",
        main_text,
    )
    main_text = re.sub(
        r"(?m)^app\.include_router\(student_survey_comparison_router\)\s*\n",
        "",
        main_text,
    )
    return main_text


def patch_main() -> None:
    main_path = PROJECT / "app" / "main.py"
    text = main_path.read_text(encoding="utf-8-sig")
    text = clean_old_attempts(text)

    if IMPORT_ANCHOR not in text:
        raise RuntimeError(
            "Khong tim thay dong import users_router trong app/main.py."
        )
    text = text.replace(
        IMPORT_ANCHOR,
        IMPORT_LINE + "\n" + IMPORT_ANCHOR,
        1,
    )

    if REGISTER_ANCHOR not in text:
        raise RuntimeError(
            "Khong tim thay dong include historical_data_router trong app/main.py."
        )
    text = text.replace(
        REGISTER_ANCHOR,
        REGISTER_ANCHOR + "\n" + REGISTER_BLOCK.rstrip(),
        1,
    )

    main_path.write_text(text, encoding="utf-8")


def remove_python_cache() -> None:
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
            "app/main.py",
            "app/routers/student_survey_comparison.py",
        ],
        cwd=PROJECT,
        check=True,
    )

    check_path = PROJECT / "check_bai_12d_15_v7.py"
    check_code = r'''from __future__ import annotations

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
'''
    check_path.write_text(check_code, encoding="utf-8")

    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(PROJECT)
    subprocess.run(
        [str(PYTHON), str(check_path)],
        cwd=PROJECT,
        env=environment,
        check=True,
    )


try:
    print("\n" + "=" * 62)
    print("CAI DAT BAI 12D-15 V7 - DOI CHIEU DIEU TRA VOI HOC SINH")
    print("=" * 62)

    if not PROJECT.exists():
        raise FileNotFoundError(f"Khong tim thay du an: {PROJECT}")
    if not SOURCE.exists():
        raise FileNotFoundError(f"Khong tim thay goi cai dat: {SOURCE}")

    BACKUP.mkdir(parents=True, exist_ok=False)

    print("\nBUOC 1 - SAO LUU MA NGUON VA CO SO DU LIEU")
    for relative in FILES_TO_BACKUP:
        current = PROJECT / relative
        if current.exists():
            copy_file(current, BACKUP / relative)
    database = PROJECT / "data" / "phocap.db"
    if database.exists():
        copy_file(database, BACKUP / "phocap.db")
    print("Ban sao an toan:", BACKUP)

    print("\nBUOC 2 - CHEP ROUTER VA GIAO DIEN")
    for relative in FILES_TO_COPY:
        source_file = SOURCE / relative
        if not source_file.exists():
            raise FileNotFoundError(f"Thieu tep trong goi cai dat: {source_file}")
        copy_file(source_file, PROJECT / relative)
        print("Da chep:", relative)

    print("\nBUOC 3 - DANG KY ROUTE DOI CHIEU TRUC TIEP VAO FASTAPI APP")
    patch_main()
    print("Da cap nhat: app/main.py")

    print("\nBUOC 4 - XOA BO NHO DEM PYTHON")
    remove_python_cache()

    print("\nBUOC 5 - KIEM TRA CU PHAP, ROUTE VA GIAO DIEN")
    run_checks()

    print("\n" + "=" * 62)
    print("CAI DAT BAI 12D-15 V7 THANH CONG")
    print("=" * 62)
    print("Ban sao an toan:", BACKUP)

except Exception as exc:
    print("\nCAI DAT KHONG THANH CONG:")
    print(exc)
    traceback.print_exc()
    if BACKUP.exists():
        restore_backup()
        print("Ban sao an toan:", BACKUP)
    sys.exit(1)
