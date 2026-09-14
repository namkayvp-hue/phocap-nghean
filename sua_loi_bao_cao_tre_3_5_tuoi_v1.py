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

THIS_DIR = Path(__file__).resolve().parent
PAYLOAD_ROUTER = THIS_DIR / "payload" / "app" / "routers" / "preschool_3_5_report.py"
PAYLOAD_TEMPLATE = THIS_DIR / "payload" / "app" / "templates" / "reports" / "preschool_3_5_report.html"
CHECKER = THIS_DIR / "check_bao_cao_tre_3_5_tuoi_v1.py"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = PROJECT / "exports" / f"backup_sua_bao_cao_tre_3_5_tuoi_v1_{STAMP}"

MARKER_START = "# === BAO_CAO_TRE_3_5_TUOI_V1_START ==="
MARKER_END = "# === BAO_CAO_TRE_3_5_TUOI_V1_END ==="

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


def restore() -> None:
    print("")
    print("DANG KHOI PHUC TRANG THAI TRUOC KHI SUA...")
    for rel in [
        Path("app/main.py"),
        Path("app/routers/preschool_3_5_report.py"),
        Path("app/templates/reports/preschool_3_5_report.html"),
        Path("data/phocap.db"),
    ]:
        saved = BACKUP / rel
        target = PROJECT / rel
        if saved.exists():
            copy_with_parent(saved, target)
    print("DA KHOI PHUC.")


def ensure_fallback_files() -> None:
    if not ROUTER.exists():
        if not PAYLOAD_ROUTER.exists():
            raise RuntimeError(
                "Khong tim thay router bao cao tre 3-5 tuoi va khong co payload du phong."
            )
        copy_with_parent(PAYLOAD_ROUTER, ROUTER)
        print("Da phuc hoi router bao cao tre 3-5 tuoi tu payload du phong.")
    else:
        print("Router bao cao tre 3-5 tuoi da ton tai - GIU NGUYEN.")

    if not TEMPLATE.exists():
        if not PAYLOAD_TEMPLATE.exists():
            raise RuntimeError(
                "Khong tim thay giao dien bao cao tre 3-5 tuoi va khong co payload du phong."
            )
        copy_with_parent(PAYLOAD_TEMPLATE, TEMPLATE)
        print("Da phuc hoi giao dien bao cao tre 3-5 tuoi tu payload du phong.")
    else:
        print("Giao dien bao cao tre 3-5 tuoi da ton tai - GIU NGUYEN.")


def update_main() -> None:
    text = MAIN.read_text(encoding="utf-8-sig")

    start = text.find(MARKER_START)
    end = text.find(MARKER_END)
    if start >= 0 and end >= start:
        end += len(MARKER_END)
        text = text[:start] + text[end:]

    block = (
        "\n\n"
        + MARKER_START
        + "\n"
        + "# Khoi phuc dang ky router BAO CAO TRE 3-5 TUOI.\n"
        + "# Chi dang ky router da ton tai; KHONG doi duong dan, KHONG doi du lieu, KHONG doi nghiep vu.\n"
        + "from app.routers.preschool_3_5_report import router as preschool_3_5_report_router\n\n"
        + '_existing_paths_3_5 = {getattr(_r, "path", "") for _r in app.routes}\n'
        + 'if "/bao-cao/pho-cap-3-5-tuoi" not in _existing_paths_3_5:\n'
        + "    app.include_router(preschool_3_5_report_router)\n"
        + MARKER_END
        + "\n"
    )

    MAIN.write_text(text.rstrip() + block, encoding="utf-8")
    print("Da dang ky router bao cao tre 3-5 tuoi vao FastAPI app.")


def clear_cache() -> None:
    for cache in (PROJECT / "app").rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)


def run_checks() -> None:
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

    db = PROJECT / "data" / "phocap.db"
    saved_db = BACKUP / "data" / "phocap.db"
    if db.exists() and saved_db.exists():
        if sha256(db) != sha256(saved_db):
            raise AssertionError(
                "data/phocap.db da bi thay doi - dung cai dat."
            )

    print("")
    print("Route cu: KHONG DOI")
    print("Du lieu: KHONG DOI")
    print("Luong nghiep vu: KHONG DOI")
    print("Bao cao 3-5 tuoi: CHI KHOI PHUC DANG KY ROUTER DA CO")


def main() -> int:
    print("")
    print("=" * 68)
    print("SUA LOI BAO CAO TRE 3-5 TUOI V1")
    print("CAP TINH - XA - TRUONG - GIAO VIEN")
    print("=" * 68)

    if not PROJECT.exists():
        print("Khong tim thay C:\\PhoCap")
        return 1
    if not PYTHON.exists():
        print("Khong tim thay Python moi truong ao.")
        return 1
    if not MAIN.exists():
        print("Khong tim thay app\\main.py")
        return 1
    if not CHECKER.exists():
        print("Khong tim thay tep kiem tra trong goi cai.")
        return 1

    BACKUP.mkdir(parents=True, exist_ok=False)
    backup_file(MAIN)
    backup_file(ROUTER)
    backup_file(TEMPLATE)
    backup_file(PROJECT / "data" / "phocap.db")

    print("")
    print("Ban sao an toan:", BACKUP)

    try:
        ensure_fallback_files()
        update_main()
        clear_cache()
        run_checks()

        print("")
        print("=" * 68)
        print("SUA LOI BAO CAO TRE 3-5 TUOI V1 THANH CONG")
        print("=" * 68)
        print("Duong dan giu nguyen:", ROUTE_PAGE)
        print("Excel giu nguyen:", ROUTE_EXCEL)
        print("Cap tinh / xa / truong / giao vien: SAN SANG THEO QUYEN HIEN CO")
        print("Ban sao an toan:", BACKUP)
        return 0
    except Exception as exc:
        print("")
        print("SUA LOI KHONG THANH CONG:")
        print(exc)
        traceback.print_exc()
        restore()
        print("Ban sao an toan:", BACKUP)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
