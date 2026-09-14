from __future__ import annotations

import hashlib
import shutil
import subprocess
import traceback
from datetime import datetime
from pathlib import Path

PROJECT = Path(r"C:\PhoCap").resolve()
PYTHON = (PROJECT / ".venv" / "Scripts" / "python.exe").resolve()

MAIN = PROJECT / "app" / "main.py"
ROUTER = PROJECT / "app" / "routers" / "preschool_3_5_report.py"
TEMPLATE = PROJECT / "app" / "templates" / "reports" / "preschool_3_5_report.html"
DB = PROJECT / "data" / "phocap.db"

THIS_DIR = Path(__file__).resolve().parent
CHECKER = THIS_DIR / "check_bao_cao_tre_3_5_tuoi_v2.py"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = PROJECT / "exports" / f"backup_sua_bao_cao_tre_3_5_tuoi_v2_{STAMP}"

OLD_START = "# === BAO_CAO_TRE_3_5_TUOI_V1_START ==="
OLD_END = "# === BAO_CAO_TRE_3_5_TUOI_V1_END ==="
START = "# === BAO_CAO_TRE_3_5_TUOI_V2_START ==="
END = "# === BAO_CAO_TRE_3_5_TUOI_V2_END ==="

ROUTE_PAGE = "/bao-cao/pho-cap-3-5-tuoi"
ROUTE_EXCEL = "/bao-cao/pho-cap-3-5-tuoi/xuat-excel"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def copy_with_parent(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def backup_file(path: Path) -> None:
    if path.exists():
        copy_with_parent(path, BACKUP / path.relative_to(PROJECT))


def remove_marker_block(text: str, start_marker: str, end_marker: str) -> str:
    while True:
        start = text.find(start_marker)
        if start < 0:
            return text
        end = text.find(end_marker, start)
        if end < 0:
            return text
        end += len(end_marker)
        text = text[:start] + text[end:]


def restore() -> None:
    print("")
    print("DANG KHOI PHUC MA NGUON TRUOC V2...")
    for rel in [
        Path("app/main.py"),
        Path("data/phocap.db"),
    ]:
        saved = BACKUP / rel
        target = PROJECT / rel
        if saved.exists():
            copy_with_parent(saved, target)

    for cache in (PROJECT / "app").rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)

    print("DA KHOI PHUC MA NGUON TRUOC V2.")


def validate_files() -> None:
    if not PROJECT.exists():
        raise RuntimeError("Khong tim thay C:\\PhoCap.")
    if not PYTHON.exists():
        raise RuntimeError("Khong tim thay Python trong .venv.")
    if not MAIN.exists():
        raise RuntimeError("Khong tim thay app\\main.py.")
    if not ROUTER.exists():
        raise RuntimeError(
            "Khong tim thay app\\routers\\preschool_3_5_report.py. "
            "Dung cai dat va gui anh Terminal."
        )
    if not TEMPLATE.exists():
        raise RuntimeError(
            "Khong tim thay app\\templates\\reports\\preschool_3_5_report.html. "
            "Dung cai dat va gui anh Terminal."
        )
    if not CHECKER.exists():
        raise RuntimeError("Khong tim thay tep kiem tra V2 trong goi cai.")


def patch_main() -> None:
    text = MAIN.read_text(encoding="utf-8-sig")
    text = remove_marker_block(text, OLD_START, OLD_END)
    text = remove_marker_block(text, START, END)

    block = r'''
# === BAO_CAO_TRE_3_5_TUOI_V2_START ===
# Dang ky TRUC TIEP cac APIRoute da co san trong router bao cao tre 3-5 tuoi.
# Giu nguyen duong dan, du lieu va luong nghiep vu.
# Cach dang ky nay dong nhat voi cac phan he hien tai cua du an.
from app.routers.preschool_3_5_report import (
    router as preschool_3_5_report_router,
)

for _preschool_3_5_route in preschool_3_5_report_router.routes:
    _preschool_3_5_exists = any(
        getattr(_existing_route, "path", None)
        == getattr(_preschool_3_5_route, "path", None)
        and getattr(_existing_route, "methods", None)
        == getattr(_preschool_3_5_route, "methods", None)
        for _existing_route in app.router.routes
    )
    if not _preschool_3_5_exists:
        app.router.routes.append(_preschool_3_5_route)
# === BAO_CAO_TRE_3_5_TUOI_V2_END ===
'''

    anchor = '\n@app.get("/", response_class=HTMLResponse)'
    if anchor in text:
        text = text.replace(anchor, "\n" + block + anchor, 1)
    else:
        text = text.rstrip() + "\n\n" + block + "\n"

    MAIN.write_text(text, encoding="utf-8")
    print("Da dang ky TRUC TIEP router bao cao tre 3-5 tuoi.")


def clear_cache() -> None:
    for cache in (PROJECT / "app").rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)


def run_checks(db_hash_before: str | None) -> None:
    subprocess.run(
        [
            str(PYTHON),
            "-m",
            "py_compile",
            str(MAIN),
            str(ROUTER),
        ],
        cwd=PROJECT,
        check=True,
    )

    subprocess.run(
        [str(PYTHON), str(CHECKER)],
        cwd=PROJECT,
        check=True,
    )

    if DB.exists() and db_hash_before is not None:
        if sha256(DB) != db_hash_before:
            raise AssertionError(
                "data/phocap.db bi thay doi. Tu dong khoi phuc."
            )


def main() -> int:
    print("")
    print("=" * 70)
    print("SUA LOI BAO CAO TRE 3-5 TUOI V2")
    print("DANG KY ROUTE TRUC TIEP - KHONG DOI ROUTE / DU LIEU / NGHIEP VU")
    print("=" * 70)

    try:
        validate_files()

        BACKUP.mkdir(parents=True, exist_ok=False)
        backup_file(MAIN)
        backup_file(DB)

        db_hash_before = sha256(DB) if DB.exists() else None

        print("")
        print("Ban sao an toan:", BACKUP)

        patch_main()
        clear_cache()
        run_checks(db_hash_before)

        print("")
        print("=" * 70)
        print("SUA LOI BAO CAO TRE 3-5 TUOI V2 THANH CONG")
        print("=" * 70)
        print("Route trang:", ROUTE_PAGE)
        print("Route Excel:", ROUTE_EXCEL)
        print("Route cu: KHONG DOI")
        print("data/phocap.db: KHONG DOI")
        print("Luong nghiep vu: KHONG DOI")
        print("Chuc nang cu: GIU NGUYEN")
        print("Ban sao an toan:", BACKUP)
        return 0

    except Exception as exc:
        print("")
        print("SUA LOI V2 KHONG THANH CONG:")
        print(exc)
        traceback.print_exc()

        if BACKUP.exists():
            restore()
            print("Ban sao an toan:", BACKUP)

        return 1


if __name__ == "__main__":
    raise SystemExit(main())
