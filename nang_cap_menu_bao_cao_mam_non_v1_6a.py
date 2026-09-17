from __future__ import annotations

import hashlib
import shutil
import subprocess
import traceback
from datetime import datetime
from pathlib import Path

PROJECT = Path(r"C:\PhoCap").resolve()
PYTHON = PROJECT / ".venv" / "Scripts" / "python.exe"
PARTIAL = PROJECT / "app" / "templates" / "partials" / "dropdown_menu_v1.html"
MAIN = PROJECT / "app" / "main.py"
DB = PROJECT / "data" / "phocap.db"
ROUTERS = PROJECT / "app" / "routers"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = PROJECT / "exports" / f"backup_menu_bao_cao_mam_non_v1_6a_{STAMP}"

NEW_MN_PANEL = (
    '                        <div class="pc-submenu-panel" role="menu">\n'
    '                            <a href="/bao-cao?report_type=PCGD_MN_M1_2025" role="menuitem">5.2.1. MN-M1 – Phổ cập giáo dục Mầm non</a>\n'
    '                            <a href="/bao-cao?report_type=PCGD_MN_02_2025" role="menuitem">5.2.2. MN-02 – Kết quả PCGD Mầm non</a>\n'
    '                            <a href="/bao-cao?report_type=PCGD_MN_01_GV_2025" role="menuitem">5.2.3. MN-01-GV – Đội ngũ giáo viên</a>\n'
    '                            <a href="/bao-cao?report_type=PCGD_MN_01_CSVC_2025" role="menuitem">5.2.4. MN-01-CSVC – Cơ sở vật chất</a>\n'
    '                            <a href="/bao-cao?report_type=PCGD_MN_TAICHINH_2025" role="menuitem">5.2.5. MN-TC – Báo cáo tài chính</a>\n'
    '                        </div>'
)


def sha256(path: Path):
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def tree_hash(root: Path):
    h = hashlib.sha256()
    if not root.exists():
        return h.hexdigest()
    for p in sorted(root.rglob("*")):
        if not p.is_file() or "__pycache__" in p.parts:
            continue
        h.update(p.relative_to(root).as_posix().encode("utf-8"))
        h.update(p.read_bytes())
    return h.hexdigest()


def copy_with_parent(src: Path, dst: Path):
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def locate_mn_submenu(text: str):
    label = "5.2. Báo cáo Mầm non"
    label_pos = text.find(label)
    if label_pos < 0:
        raise RuntimeError("Khong tim thay nhom 5.2 Bao cao Mam non.")

    panel_start = text.find(
        '<div class="pc-submenu-panel" role="menu">',
        label_pos,
    )
    if panel_start < 0:
        raise RuntimeError("Khong tim thay panel Bao cao Mam non.")

    panel_end = text.find("</div>", panel_start)
    if panel_end < 0:
        raise RuntimeError("Khong tim thay diem ket thuc panel.")

    return panel_start, panel_end + len("</div>")


def patch_menu():
    text = PARTIAL.read_text(encoding="utf-8-sig")
    start, end = locate_mn_submenu(text)
    new_text = text[:start] + NEW_MN_PANEL + text[end:]

    new_start, new_end = locate_mn_submenu(new_text)
    mn_panel = new_text[new_start:new_end]

    forbidden = [
        "Báo cáo tổng hợp điều tra",
        "Báo cáo trẻ 3–5 tuổi",
        "Bộ biểu mẫu PCGDMN 2025",
        "Biến động – theo dõi",
        "Đối chiếu điều tra với học sinh",
        "Tiến độ – đôn đốc",
        "Báo cáo hỗ trợ đã hoàn thành",
    ]

    found = [x for x in forbidden if x in mn_panel]
    if found:
        raise RuntimeError("Nhom 5.2 van con muc cu: " + ", ".join(found))

    required = [
        "5.2.1. MN-M1 – Phổ cập giáo dục Mầm non",
        "5.2.2. MN-02 – Kết quả PCGD Mầm non",
        "5.2.3. MN-01-GV – Đội ngũ giáo viên",
        "5.2.4. MN-01-CSVC – Cơ sở vật chất",
        "5.2.5. MN-TC – Báo cáo tài chính",
    ]
    missing = [x for x in required if x not in mn_panel]
    if missing:
        raise RuntimeError("Thieu muc moi: " + ", ".join(missing))

    center_link = '<a href="/bao-cao" role="menuitem">5.1. Trung tâm báo cáo</a>'
    if center_link not in new_text:
        raise RuntimeError("Muc 5.1 Trung tam bao cao bi thay doi.")

    for group in [
        "5.3. Báo cáo Tiểu học",
        "5.4. Báo cáo THCS",
        "5.5. Báo cáo Xóa mù chữ",
    ]:
        if group not in new_text:
            raise RuntimeError("Menu bi mat nhom cu: " + group)

    PARTIAL.write_text(new_text, encoding="utf-8")


def clear_cache():
    for cache in (PROJECT / "app").rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)


def main():
    print("")
    print("=" * 72)
    print("MENU BAO CAO MAM NON V1.6A")
    print("CHI DOI MENU - KHONG DOI ROUTE / DU LIEU / NGHIEP VU")
    print("=" * 72)

    if not PARTIAL.exists():
        print("Khong tim thay:", PARTIAL)
        return 1
    if not PYTHON.exists():
        print("Khong tim thay Python .venv")
        return 1

    BACKUP.mkdir(parents=True, exist_ok=False)
    copy_with_parent(
        PARTIAL,
        BACKUP / PARTIAL.relative_to(PROJECT),
    )

    main_hash_before = sha256(MAIN)
    db_hash_before = sha256(DB)
    routers_hash_before = tree_hash(ROUTERS)

    print("Ban sao an toan:", BACKUP)

    try:
        patch_menu()
        clear_cache()

        check_file = PROJECT / "check_menu_bao_cao_mam_non_v1_6a.py"
        check_code = (
            "from pathlib import Path\n"
            "from jinja2 import Environment, FileSystemLoader\n"
            "root = Path(r'C:\\\\PhoCap\\\\app\\\\templates')\n"
            "env = Environment(loader=FileSystemLoader(str(root)))\n"
            "env.get_template('partials/dropdown_menu_v1.html')\n"
            "print('Jinja: DAT')\n"
        )
        check_file.write_text(check_code, encoding="utf-8")

        subprocess.run(
            [str(PYTHON), str(check_file)],
            cwd=PROJECT,
            check=True,
        )

        if sha256(MAIN) != main_hash_before:
            raise RuntimeError("app/main.py bi thay doi.")
        if sha256(DB) != db_hash_before:
            raise RuntimeError("data/phocap.db bi thay doi.")
        if tree_hash(ROUTERS) != routers_hash_before:
            raise RuntimeError("app/routers bi thay doi.")

        print("")
        print("Menu 5.2: CHI CON 5 BIEU MAM NON CHINH THUC")
        print("5.1 Trung tam bao cao: GIU NGUYEN")
        print("Menu Tieu hoc / THCS / XMC: GIU NGUYEN")
        print("app/main.py: KHONG DOI")
        print("app/routers: KHONG DOI")
        print("data/phocap.db: KHONG DOI")
        print("Route: KHONG DOI")
        print("Luong nghiep vu: KHONG DOI")
        print("Chuc nang cu: KHONG XOA")
        print("")
        print("MENU BAO CAO MAM NON V1.6A THANH CONG")
        print("Ban sao an toan:", BACKUP)
        return 0

    except Exception as exc:
        print("")
        print("CAI DAT KHONG THANH CONG:")
        print(exc)
        traceback.print_exc()

        saved = BACKUP / PARTIAL.relative_to(PROJECT)
        if saved.exists():
            copy_with_parent(saved, PARTIAL)
            print("DA KHOI PHUC MENU CU.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
