from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path


PROJECT = Path(r"C:\PhoCap").resolve()

PACKAGE = Path(
    r"C:\PhoCap\exports"
    r"\Bai_12D_15_V2_Doi_chieu_du_lieu_hoc_sinh"
).resolve()

SOURCE = PACKAGE / "tep_thay_the"
PYTHON = Path(sys.executable).resolve()

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

BACKUP = (
    PROJECT
    / "exports"
    / f"backup_bai_12d_15_v4_{STAMP}"
)


TARGETS = [
    Path("app/__init__.py"),
    Path("app/routers/__init__.py"),
    Path("app/main.py"),
    Path("app/routers/surveys.py"),
    Path(
        "app/routers/"
        "student_survey_comparison.py"
    ),
    Path(
        "app/templates/surveys/"
        "student_survey_comparison.html"
    ),
    Path(
        "app/templates/surveys/"
        "summary_report.html"
    ),
    Path(
        "app/templates/surveys/"
        "households.html"
    ),
]


COPY_FROM_PACKAGE = [
    Path("app/__init__.py"),
    Path("app/routers/__init__.py"),
    Path(
        "app/routers/"
        "student_survey_comparison.py"
    ),
    Path(
        "app/templates/surveys/"
        "student_survey_comparison.html"
    ),
    Path(
        "app/templates/surveys/"
        "summary_report.html"
    ),
    Path(
        "app/templates/surveys/"
        "households.html"
    ),
]


MARKER_START = (
    "# === BAI 12D-15 V4: BAT DAU ==="
)

MARKER_END = (
    "# === BAI 12D-15 V4: KET THUC ==="
)

INTEGRATION_BLOCK = f"""

{MARKER_START}
from app.routers.student_survey_comparison import (
    router as student_survey_comparison_router,
)

router.include_router(
    student_survey_comparison_router
)
{MARKER_END}
"""


def copy_file(
    source: Path,
    destination: Path,
) -> None:
    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    shutil.copy2(
        source,
        destination,
    )


def restore() -> None:
    print("")
    print(
        "DANG KHOI PHUC MA NGUON CU..."
    )

    for relative in TARGETS:
        saved = BACKUP / relative
        current = PROJECT / relative

        if saved.exists():
            copy_file(
                saved,
                current,
            )
        elif current.exists():
            current.unlink()

    print(
        "DA KHOI PHUC MA NGUON CU."
    )


try:
    print("")
    print(
        "=" * 60
    )
    print(
        "CAI DAT BAI 12D-15 V4"
    )
    print(
        "DANG KY QUA ROUTER DIEU TRA"
    )
    print(
        "=" * 60
    )

    if not PROJECT.exists():
        raise FileNotFoundError(
            f"Khong tim thay du an: "
            f"{PROJECT}"
        )

    if not SOURCE.exists():
        raise FileNotFoundError(
            "Khong tim thay thu muc "
            f"tep_thay_the: {SOURCE}"
        )

    BACKUP.mkdir(
        parents=True,
        exist_ok=False,
    )

    print("")
    print(
        "BUOC 1 - SAO LUU MA NGUON"
    )

    for relative in TARGETS:
        current = PROJECT / relative

        if current.exists():
            copy_file(
                current,
                BACKUP / relative,
            )

    database = (
        PROJECT
        / "data"
        / "phocap.db"
    )

    if database.exists():
        copy_file(
            database,
            BACKUP / "phocap.db",
        )

    print(
        "Ban sao an toan:",
        BACKUP,
    )

    print("")
    print(
        "BUOC 2 - CHEP ROUTER "
        "VA GIAO DIEN"
    )

    for relative in COPY_FROM_PACKAGE:
        source_file = SOURCE / relative

        if not source_file.exists():
            raise FileNotFoundError(
                "Thieu tep trong goi cai dat: "
                f"{source_file}"
            )

        copy_file(
            source_file,
            PROJECT / relative,
        )

        print(
            "Da chep:",
            relative,
        )

    print("")
    print(
        "BUOC 3 - DIEU CHINH "
        "PREFIX ROUTER CON"
    )

    router_path = (
        PROJECT
        / "app"
        / "routers"
        / "student_survey_comparison.py"
    )

    router_text = router_path.read_text(
        encoding="utf-8-sig"
    )

    router_text, changed = re.subn(
        (
            r'(?m)^'
            r'\s{4}'
            r'prefix="/dieu-tra",'
            r'\s*\n'
        ),
        "",
        router_text,
        count=1,
    )

    if (
        changed != 1
        and 'prefix="/dieu-tra"'
        in router_text
    ):
        raise RuntimeError(
            "Khong the bo prefix "
            "/dieu-tra trong router con."
        )

    router_path.write_text(
        router_text,
        encoding="utf-8",
    )

    print("")
    print(
        "BUOC 4 - GAN ROUTER CON "
        "VAO ROUTER DIEU TRA"
    )

    surveys_path = (
        PROJECT
        / "app"
        / "routers"
        / "surveys.py"
    )

    surveys_text = surveys_path.read_text(
        encoding="utf-8-sig"
    )

    surveys_text = re.sub(
        (
            re.escape(MARKER_START)
            + r".*?"
            + re.escape(MARKER_END)
            + r"\s*"
        ),
        "",
        surveys_text,
        flags=re.DOTALL,
    ).rstrip()

    surveys_path.write_text(
        surveys_text
        + INTEGRATION_BLOCK,
        encoding="utf-8",
    )

    print("")
    print(
        "BUOC 5 - LOAI BO "
        "DANG KY TRUC TIEP CU"
    )

    main_path = (
        PROJECT
        / "app"
        / "main.py"
    )

    main_text = main_path.read_text(
        encoding="utf-8-sig"
    )

    main_text = re.sub(
        (
            r"(?m)^from "
            r"app\.routers\."
            r"student_survey_comparison "
            r"import router as "
            r"student_survey_comparison_router"
            r"\s*\n"
        ),
        "",
        main_text,
    )

    main_text = re.sub(
        (
            r"(?m)^app\.include_router"
            r"\("
            r"student_survey_comparison_router"
            r"\)"
            r"\s*\n"
        ),
        "",
        main_text,
    )

    if (
        "student_survey_comparison"
        in main_text
    ):
        raise RuntimeError(
            "main.py van con dong "
            "dang ky doi chieu cu."
        )

    main_path.write_text(
        main_text,
        encoding="utf-8",
    )

    print("")
    print(
        "BUOC 6 - XOA BO NHO DEM PYTHON"
    )

    for cache in (
        PROJECT / "app"
    ).rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(
                cache,
                ignore_errors=True,
            )

    print("")
    print(
        "BUOC 7 - KIEM TRA CU PHAP"
    )

    subprocess.run(
        [
            str(PYTHON),
            "-m",
            "py_compile",
            "app/main.py",
            "app/routers/surveys.py",
            (
                "app/routers/"
                "student_survey_comparison.py"
            ),
        ],
        cwd=PROJECT,
        check=True,
    )

    print("")
    print(
        "BUOC 8 - KIEM TRA "
        "ROUTE THUC TE"
    )

    check_code = r'''
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
'''

    environment = os.environ.copy()

    environment["PYTHONPATH"] = str(
        PROJECT
    )

    check_path = (
        PROJECT
        / "check_bai_12d_15_v5.py"
    )

    check_path.write_text(
        check_code,
        encoding="utf-8",
    )

    subprocess.run(
        [
            str(PYTHON),
            str(check_path),
        ],
        cwd=PROJECT,
        env=environment,
        check=True,
    )

    print("")
    print(
        "=" * 60
    )
    print(
        "CAI DAT BAI 12D-15 "
        "V4 THANH CONG"
    )
    print(
        "=" * 60
    )
    print(
        "Ban sao an toan:",
        BACKUP,
    )

except Exception as exc:
    print("")
    print(
        "CAI DAT KHONG THANH CONG:"
    )
    print(exc)

    traceback.print_exc()

    if BACKUP.exists():
        restore()

        print(
            "Ban sao an toan:",
            BACKUP,
        )

    sys.exit(1)

