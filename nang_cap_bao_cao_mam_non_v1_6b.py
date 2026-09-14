from __future__ import annotations

import ast
import hashlib
import json
import re
import shutil
import subprocess
import traceback
from datetime import datetime
from pathlib import Path

PROJECT = Path(r"C:\PhoCap").resolve()
PYTHON = PROJECT / ".venv" / "Scripts" / "python.exe"
MAIN = PROJECT / "app" / "main.py"
DB = PROJECT / "data" / "phocap.db"
ROUTER = PROJECT / "app" / "routers" / "report_center.py"
HTML = PROJECT / "app" / "templates" / "reports" / "report_center.html"
MENU = PROJECT / "app" / "templates" / "partials" / "dropdown_menu_v1.html"
BUILDER = PROJECT / "app" / "pcgd_mn_report_builders_v1.py"
TEMPLATE_ROOT = PROJECT / "app" / "report_templates" / "pcgd_mn_2025"
ROUTERS_DIR = PROJECT / "app" / "routers"

HERE = Path(__file__).resolve().parent
PAYLOAD = HERE / "payload"
PAYLOAD_TEMPLATES = PAYLOAD / "templates"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = PROJECT / "exports" / f"backup_bao_cao_mam_non_v1_6b_{STAMP}"
MANIFEST = BACKUP / "manifest.json"

MN_CODES = [
    "PCGD_MN_M1_2025",
    "PCGD_MN_02_2025",
    "PCGD_MN_01_GV_2025",
    "PCGD_MN_01_CSVC_2025",
    "PCGD_MN_TAICHINH_2025",
]
TEMPLATE_FILES = [
    "PCGD_2025_MN_M1.xlsx",
    "PCGD_2025_MN_02.xlsx",
    "PCGD_2025_MN_01_GV.xlsx",
    "PCGD_2025_MN_01_CSVC.xlsx",
    "PCGD_2025_MN_TAICHINH.xlsx",
]
REPORT_START = "# === PCGD_MN_REPORT_TYPES_V1_6B_START ==="
REPORT_END = "# === PCGD_MN_REPORT_TYPES_V1_6B_END ==="
EXPORT_START = "# === PCGD_MN_EXPORT_V1_6B_START ==="
EXPORT_END = "# === PCGD_MN_EXPORT_V1_6B_END ==="


def sha256(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def route_signatures(routers_dir: Path) -> list[tuple[str, str, str, str]]:
    result: list[tuple[str, str, str, str]] = []
    for path in sorted(routers_dir.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for deco in node.decorator_list:
                if not isinstance(deco, ast.Call) or not isinstance(deco.func, ast.Attribute):
                    continue
                owner = deco.func.value
                if not isinstance(owner, ast.Name) or owner.id != "router":
                    continue
                method = deco.func.attr.lower()
                if method not in {"get", "post", "put", "delete", "patch", "options", "head"}:
                    continue
                route_path = ""
                if deco.args and isinstance(deco.args[0], ast.Constant) and isinstance(deco.args[0].value, str):
                    route_path = deco.args[0].value
                result.append((path.name, method, route_path, node.name))
    return sorted(result)


def copy_with_parent(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def backup_file(path: Path, manifest: dict[str, dict[str, bool]]) -> None:
    rel = path.relative_to(PROJECT).as_posix()
    manifest[rel] = {"existed": path.exists()}
    if path.exists():
        copy_with_parent(path, BACKUP / rel)


def restore(manifest: dict[str, dict[str, bool]]) -> None:
    print("\nDANG KHOI PHUC TRANG THAI TRUOC V1.6B...")
    for rel, info in manifest.items():
        target = PROJECT / rel
        saved = BACKUP / rel
        if info.get("existed"):
            copy_with_parent(saved, target)
        elif target.exists() and target.is_file():
            target.unlink()
    print("DA KHOI PHUC AN TOAN.")


def strip_marker(text: str, start: str, end: str) -> str:
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end) + r"\s*\n?", re.S)
    return pattern.sub("", text)


def patch_report_types(text: str) -> str:
    text = strip_marker(text, REPORT_START, REPORT_END)
    for code in MN_CODES:
        # Refuse ambiguous partially-installed definitions outside our marker.
        if f'"{code}"' in text:
            raise RuntimeError(
                f"report_center.py da co {code} ngoai khoi V1.6B. "
                "Hay gui anh Terminal de kiem tra truoc khi ghi de."
            )
    report_pos = text.find("REPORT_TYPES:")
    status_pos = text.find("\nSTATUS_LABELS =", report_pos)
    if report_pos < 0 or status_pos < 0:
        raise RuntimeError("Khong tim thay khoi REPORT_TYPES/STATUS_LABELS.")
    close_pos = text.rfind("\n}", report_pos, status_pos)
    if close_pos < 0:
        raise RuntimeError("Khong tim thay diem dong REPORT_TYPES.")
    block = (PAYLOAD / "report_types_block.txt").read_text(encoding="utf-8")
    return text[:close_pos] + "\n" + block.rstrip() + text[close_pos:]


def patch_export_branch(text: str) -> str:
    text = strip_marker(text, EXPORT_START, EXPORT_END)
    route_anchor = '@router.get("/xuat-danh-muc-excel")'
    route_pos = text.find(route_anchor)
    if route_pos < 0:
        raise RuntimeError("Khong tim thay route xuat Excel hien co.")
    next_decorator = text.find("\n@router.", route_pos + len(route_anchor))
    if next_decorator < 0:
        next_decorator = len(text)
    segment = text[route_pos:next_decorator]
    rows_anchor = "    rows, summary = _build_report_rows("
    local_pos = segment.find(rows_anchor)
    if local_pos < 0:
        raise RuntimeError("Khong tim thay vi tri truoc luong xuat danh muc cu.")
    insert_pos = route_pos + local_pos
    block = (PAYLOAD / "export_branch.txt").read_text(encoding="utf-8")
    return text[:insert_pos] + block + text[insert_pos:]


def replace_51_with_submenu(text: str) -> str:
    block = (PAYLOAD / "center_submenu.html").read_text(encoding="utf-8").rstrip()
    # Already installed: replace the existing 5.1 submenu deterministically.
    label_pos = text.find("5.1. Trung tâm báo cáo")
    if label_pos < 0:
        raise RuntimeError("Khong tim thay muc 5.1 Trung tam bao cao.")

    direct_re = re.compile(r'<a\s+href="/bao-cao"\s+role="menuitem">5\.1\. Trung tâm báo cáo</a>')
    if direct_re.search(text):
        return direct_re.sub(block, text, count=1)

    # If already a submenu, find its enclosing pc-submenu div by searching backward.
    start = text.rfind('<div class="pc-submenu">', 0, label_pos)
    if start < 0:
        raise RuntimeError("5.1 khong phai link truc tiep va cung khong tim thay submenu hien co.")
    panel_start = text.find('<div class="pc-submenu-panel" role="menu">', label_pos)
    if panel_start < 0:
        raise RuntimeError("Khong tim thay panel 5.1 hien co.")
    panel_end = text.find("</div>", panel_start)
    if panel_end < 0:
        raise RuntimeError("Khong tim thay ket thuc panel 5.1.")
    outer_end = text.find("</div>", panel_end + len("</div>"))
    if outer_end < 0:
        raise RuntimeError("Khong tim thay ket thuc submenu 5.1.")
    outer_end += len("</div>")
    return text[:start] + block + text[outer_end:]


def replace_52_panel(text: str) -> str:
    label_pos = text.find("5.2. Báo cáo Mầm non")
    if label_pos < 0:
        raise RuntimeError("Khong tim thay 5.2 Bao cao Mam non.")
    panel_start = text.find('<div class="pc-submenu-panel" role="menu">', label_pos)
    panel_end = text.find("</div>", panel_start)
    if panel_start < 0 or panel_end < 0:
        raise RuntimeError("Khong tim thay panel 5.2.")
    panel_end += len("</div>")
    block = (PAYLOAD / "mn_submenu.html").read_text(encoding="utf-8").rstrip()
    return text[:panel_start] + block + text[panel_end:]


def patch_menu(text: str) -> str:
    text = replace_51_with_submenu(text)
    text = replace_52_panel(text)
    required = [
        "5.1.1. Báo cáo tổng hợp điều tra",
        "5.1.2. Biến động – theo dõi",
        "5.1.3. Đối chiếu điều tra với học sinh",
        "5.1.4. Tiến độ – đôn đốc",
        "5.2.1. MN-M1 – Phổ cập giáo dục Mầm non",
        "5.2.5. MN-TC – Báo cáo tài chính",
        "5.3. Báo cáo Tiểu học",
        "5.4. Báo cáo THCS",
        "5.5. Báo cáo Xóa mù chữ",
    ]
    for item in required:
        if item not in text:
            raise RuntimeError("Menu sau sua thieu: " + item)
    forbidden_in_52 = [
        "Báo cáo trẻ 3–5 tuổi",
        "Báo cáo hỗ trợ đã hoàn thành",
        "Bộ biểu mẫu PCGDMN 2025",
    ]
    pos = text.find("5.2. Báo cáo Mầm non")
    pstart = text.find('<div class="pc-submenu-panel" role="menu">', pos)
    pend = text.find("</div>", pstart)
    panel = text[pstart:pend]
    for item in forbidden_in_52:
        if item in panel:
            raise RuntimeError("5.2 van con muc cu: " + item)
    return text


def patch_html(text: str) -> str:
    # Current report-center template already has an official-export list for TH/THCS/XMC.
    pattern = re.compile(r"(\{%\s*if\s+selected_report_type\s+in\s*\[)(.*?)(\]\s*%\})", re.S)
    match = pattern.search(text)
    if match:
        body = match.group(2)
        for code in MN_CODES:
            literal = repr(code)
            if literal not in body:
                body = body.rstrip() + ", " + literal
        return text[:match.start()] + match.group(1) + body + match.group(3) + text[match.end():]

    # Compatibility with the earlier TH-M1-only condition.
    old = re.compile(r"\{%\s*if\s+selected_report_type\s*==\s*'PCGD_TH_M1_2025'\s*%\}", re.S)
    m = old.search(text)
    if m:
        codes = ["PCGD_TH_M1_2025"] + MN_CODES
        replacement = "{% if selected_report_type in [" + ", ".join(repr(x) for x in codes) + "] %}"
        return text[:m.start()] + replacement + text[m.end():]

    raise RuntimeError("Khong tim thay dieu kien nut 'Xuat bieu' trong report_center.html.")


def main() -> int:
    print("\n" + "=" * 80)
    print("BAO CAO MAM NON V1.6B - TRUNG TAM BAO CAO + 5 MAU CHINH THUC")
    print("GIU NGUYEN ROUTE - CSDL - LUONG NGHIEP VU - CHUC NANG CU")
    print("=" * 80)

    required = [PROJECT, PYTHON, MAIN, DB, ROUTER, HTML, MENU, ROUTERS_DIR, PAYLOAD]
    for path in required:
        if not path.exists():
            print("Khong tim thay:", path)
            return 1
    for filename in TEMPLATE_FILES:
        if not (PAYLOAD_TEMPLATES / filename).exists():
            print("Thieu mau trong goi:", filename)
            return 1

    before_main = sha256(MAIN)
    before_db = sha256(DB)
    before_routes = route_signatures(ROUTERS_DIR)

    manifest: dict[str, dict[str, bool]] = {}
    BACKUP.mkdir(parents=True, exist_ok=False)
    targets = [ROUTER, HTML, MENU, BUILDER]
    targets.extend(TEMPLATE_ROOT / filename for filename in TEMPLATE_FILES)
    for target in targets:
        backup_file(target, manifest)
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Ban sao an toan:", BACKUP)

    try:
        TEMPLATE_ROOT.mkdir(parents=True, exist_ok=True)
        shutil.copy2(PAYLOAD / "pcgd_mn_report_builders_v1.py", BUILDER)
        for filename in TEMPLATE_FILES:
            shutil.copy2(PAYLOAD_TEMPLATES / filename, TEMPLATE_ROOT / filename)

        menu_text = patch_menu(MENU.read_text(encoding="utf-8-sig"))
        MENU.write_text(menu_text, encoding="utf-8")

        router_text = ROUTER.read_text(encoding="utf-8-sig")
        router_text = patch_report_types(router_text)
        router_text = patch_export_branch(router_text)
        ROUTER.write_text(router_text, encoding="utf-8")

        html_text = patch_html(HTML.read_text(encoding="utf-8-sig"))
        HTML.write_text(html_text, encoding="utf-8")

        for cache in (PROJECT / "app").rglob("__pycache__"):
            if cache.is_dir():
                shutil.rmtree(cache, ignore_errors=True)

        subprocess.run(
            [str(PYTHON), "-m", "py_compile", str(ROUTER), str(BUILDER)],
            cwd=PROJECT,
            check=True,
        )

        check_jinja = PROJECT / "check_mn_v1_6b_jinja.py"
        check_jinja.write_text(
            "from pathlib import Path\n"
            "from jinja2 import Environment, FileSystemLoader\n"
            "root=Path(r'C:\\\\PhoCap\\\\app\\\\templates')\n"
            "env=Environment(loader=FileSystemLoader(str(root)))\n"
            "env.get_template('partials/dropdown_menu_v1.html')\n"
            "env.get_template('reports/report_center.html')\n"
            "print('Jinja: DAT')\n",
            encoding="utf-8",
        )
        subprocess.run([str(PYTHON), str(check_jinja)], cwd=PROJECT, check=True)

        check_templates = PROJECT / "check_mn_v1_6b_templates.py"
        check_templates.write_text(
            "from io import BytesIO\n"
            "from pathlib import Path\n"
            "from openpyxl import load_workbook\n"
            "root=Path(r'C:\\\\PhoCap\\\\app\\\\report_templates\\\\pcgd_mn_2025')\n"
            "files=['PCGD_2025_MN_M1.xlsx','PCGD_2025_MN_02.xlsx','PCGD_2025_MN_01_GV.xlsx','PCGD_2025_MN_01_CSVC.xlsx','PCGD_2025_MN_TAICHINH.xlsx']\n"
            "for name in files:\n"
            "    p=root/name\n"
            "    wb=load_workbook(p)\n"
            "    out=BytesIO(); wb.save(out)\n"
            "    assert len(out.getvalue())>1000\n"
            "    print('DAT:',name,'->',wb.sheetnames)\n"
            "print('5 MAU XLSX: DAT')\n",
            encoding="utf-8",
        )
        subprocess.run([str(PYTHON), str(check_templates)], cwd=PROJECT, check=True)

        if sha256(MAIN) != before_main:
            raise RuntimeError("app/main.py da bi thay doi.")
        if sha256(DB) != before_db:
            raise RuntimeError("data/phocap.db da bi thay doi.")
        if route_signatures(ROUTERS_DIR) != before_routes:
            raise RuntimeError("Danh sach route da thay doi.")

        final_router = ROUTER.read_text(encoding="utf-8-sig")
        for code in MN_CODES:
            if f'"{code}"' not in final_router:
                raise RuntimeError("Thieu report type: " + code)
        if "normalized_report_type in PCGD_MN_SUPPORTED_REPORT_TYPES" not in final_router:
            raise RuntimeError("Chua gan nhanh xuat 5 bieu Mam non vao route Excel hien co.")

        print("\nTRUNG TAM BAO CAO 5.1: DA CO MENU SO XUONG")
        print("  5.1.1 Tong hop dieu tra")
        print("  5.1.2 Bien dong - theo doi")
        print("  5.1.3 Doi chieu dieu tra voi hoc sinh")
        print("  5.1.4 Tien do - don doc")
        print("BAO CAO MAM NON 5.2: DA CO 5 BIEU CHINH THUC")
        print("5 MAU XLSX: DA KIEM TRA MO/LUU")
        print("MN-M1 / MN-02 / MN-01-GV: TU DONG CAC CHI TIEU CO NGUON RO")
        print("MN-01-CSVC: TU DONG SO LOP; CHI TIEU CSVC CHUA CO NGUON DE TRONG")
        print("MN-TC: CHUA CO PHAN HE TAI CHINH -> DE TRONG, KHONG SUY DIEN")
        print("\napp/main.py: KHONG DOI")
        print("Route: KHONG DOI")
        print("data/phocap.db: KHONG DOI")
        print("Luong nghiep vu: KHONG DOI")
        print("Chuc nang cu: GIU NGUYEN")
        print("\nCAI DAT BAO CAO MAM NON V1.6B THANH CONG")
        print("Ban sao an toan:", BACKUP)
        return 0

    except Exception as exc:
        print("\nCAI DAT V1.6B KHONG THANH CONG:")
        print(exc)
        traceback.print_exc()
        restore(manifest)
        print("Ban sao an toan:", BACKUP)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
