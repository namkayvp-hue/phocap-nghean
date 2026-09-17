from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path

PROJECT = Path(r"C:\PhoCap")
VERSION = "BAI-13C-1-TH-M1-V2-TOAN-TINH"
ROUTER_REL = Path("app/routers/report_center.py")
HTML_REL = Path("app/templates/reports/report_center.html")
MAIN_REL = Path("app/main.py")
DB_REL = Path("data/phocap.db")
V1_MARKER_START = "# === BAI_13C_1_TH_M1_START ==="
V1_MARKER_END = "# === BAI_13C_1_TH_M1_END ==="
V2_MARKER = "# === BAI_13C_1_TH_M1_V2_TOAN_TINH ==="


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def copy_with_parent(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def collect_route_signatures(text: str) -> list[str]:
    signatures = re.findall(
        r"@router\.(get|post|put|delete|patch)\(\s*([\"'][^\"']*[\"'])",
        text,
    )
    return [f"{method}:{path}" for method, path in signatures]


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"Khong tim thay vi tri can sua: {label}")
    return text.replace(old, new, 1)


def main() -> int:
    project = PROJECT if len(sys.argv) < 2 else Path(sys.argv[1]).expanduser().resolve()
    router_path = project / ROUTER_REL
    html_path = project / HTML_REL
    main_path = project / MAIN_REL
    db_path = project / DB_REL

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = project / "exports" / f"backup_bai_13c_1_th_m1_v2_toan_tinh_{stamp}"
    backup.mkdir(parents=True, exist_ok=False)

    changed = [ROUTER_REL, HTML_REL]
    manifest = {
        "version": VERSION,
        "changed_files": [rel.as_posix() for rel in changed],
        "created_files": [],
    }

    print("\n" + "=" * 78)
    print("BAI 13C-1 - TH-M1 V2 - BAO CAO TOAN TINH")
    print("=" * 78)
    print("Nguyen tac: KHONG DOI ROUTE - KHONG DOI DU LIEU - KHONG DOI LUONG NGHIEP VU")

    try:
        for required in (router_path, html_path, main_path, db_path):
            if not required.exists():
                raise FileNotFoundError(f"Khong tim thay: {required}")

        print("\nBUOC 1 - SAO LUU AN TOAN")
        for rel in changed:
            copy_with_parent(project / rel, backup / rel)
        (backup / "BAI_13C_1_TH_M1_V2_MANIFEST.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8-sig",
        )
        latest = project / "exports" / "bai_13c_1_th_m1_v2_backup_moi_nhat.txt"
        latest.write_text(str(backup), encoding="utf-8-sig")
        print("Ban sao an toan:", backup)

        main_hash_before = sha256(main_path)
        db_hash_before = sha256(db_path)
        old_router_text = router_path.read_text(encoding="utf-8-sig")
        old_route_signatures = collect_route_signatures(old_router_text)

        if V1_MARKER_START not in old_router_text or V1_MARKER_END not in old_router_text:
            raise RuntimeError(
                "Chua tim thay logic TH-M1 V1. Hay cai BAI 13C-1 TH-M1 V1 truoc khi cai V2."
            )

        print("\nBUOC 2 - CHUYEN BIEU TH-M1 SANG PHAM VI TOAN TINH")
        text = old_router_text

        old_scope_block = '''    # Chỉ thay nội dung dữ liệu; giữ nguyên tên sheet, merge, font, border,\n    # kích thước dòng/cột, vùng in và bố cục mẫu gốc.\n    scope_title = _th_m1_scope_title(scope_label, selected_commune_id)\n    ws["A1"] = "Tỉnh: Nghệ An"\n    ws["A2"] = scope_title\n    ws["E2"] = f"Thời điểm: ngày 30 tháng 9 năm {reference_year}"\n    ws["J44"] = f"{scope_title}, ngày      tháng      năm {reference_year}"\n'''

        new_scope_block = '''    # Chỉ thay nội dung dữ liệu; giữ nguyên merge, font, border, kích thước\n    # dòng/cột, vùng in và bố cục mẫu gốc. Khi phạm vi là toàn tỉnh,\n    # biểu được nhận diện rõ là biểu cấp tỉnh; khi chọn xã/phường, mẫu xã\n    # vẫn giữ nguyên để không làm mất chức năng cũ.\n    is_province_scope = selected_commune_id is None and selected_school_id is None\n    scope_title = (\n        "Toàn tỉnh"\n        if is_province_scope\n        else _th_m1_scope_title(scope_label, selected_commune_id)\n    )\n\n    if is_province_scope and ws.title != "Toàn tỉnh":\n        ws.title = "Toàn tỉnh"\n\n    ws["A1"] = "Tỉnh: Nghệ An"\n    ws["A2"] = scope_title\n    ws["E2"] = f"Thời điểm: ngày 30 tháng 9 năm {reference_year}"\n\n    if is_province_scope:\n        ws["J44"] = f"Nghệ An, ngày      tháng      năm {reference_year}"\n        ws["J45"] = "XÁC NHẬN CỦA SỞ GIÁO DỤC VÀ ĐÀO TẠO"\n        ws["J46"] = "GIÁM ĐỐC"\n    else:\n        ws["J44"] = f"{scope_title}, ngày      tháng      năm {reference_year}"\n        ws["J45"] = "XÁC NHẬN CỦA UBND XÃ/PHƯỜNG"\n        ws["J46"] = "PHÓ CHỦ TỊCH"\n'''

        if V2_MARKER not in text:
            text = replace_once(
                text,
                old_scope_block,
                V2_MARKER + "\n" + new_scope_block,
                "khoi pham vi TH-M1 cap tinh",
            )
        else:
            print("Logic V2 da co - bo qua sua lap lai report_center.py.")

        router_path.write_text(text, encoding="utf-8")

        print("Da cau hinh khi chon Toan tinh:")
        print(" - Ten sheet: Toan tinh")
        print(" - Dong dia ban: Toan tinh")
        print(" - Dong ngay ky: Nghe An")
        print(" - Xac nhan: So Giao duc va Dao tao / Giam doc")
        print("Khi chon xa/phuong: GIU NGUYEN mau va xac nhan cap xa.")

        print("\nBUOC 3 - SUA NHAN NUT XUAT TH-M1")
        html = html_path.read_text(encoding="utf-8-sig")

        # V1 dùng nhầm biến report_type; giao diện thực tế dùng selected_report_type.
        html = html.replace(
            "{% if report_type == 'PCGD_TH_M1_2025' %}",
            "{% if selected_report_type == 'PCGD_TH_M1_2025' %}",
        )

        if "Xuất biểu TH-M1 Excel" not in html:
            old_button = '<a class="button button-success" href="{{ export_url }}">📊 Xuất danh mục Excel</a>'
            new_button = '''{% if selected_report_type == 'PCGD_TH_M1_2025' %}\n                <a class="button button-success" href="{{ export_url }}">📘 Xuất biểu TH-M1 Excel</a>\n                {% else %}\n                <a class="button button-success" href="{{ export_url }}">📊 Xuất danh mục Excel</a>\n                {% endif %}'''
            html = replace_once(html, old_button, new_button, "nut xuat TH-M1")

        html_path.write_text(html, encoding="utf-8")

        print("\nBUOC 4 - KIEM TRA AN TOAN")
        subprocess.run(
            [sys.executable, "-m", "py_compile", str(router_path)],
            cwd=project,
            check=True,
        )

        from jinja2 import Environment
        Environment().parse(html_path.read_text(encoding="utf-8-sig"))

        new_router_text = router_path.read_text(encoding="utf-8-sig")
        new_route_signatures = collect_route_signatures(new_router_text)
        if old_route_signatures != new_route_signatures:
            raise AssertionError("Danh sach route da thay doi - tu dong khoi phuc.")
        if sha256(main_path) != main_hash_before:
            raise AssertionError("app/main.py bi thay doi - tu dong khoi phuc.")
        if sha256(db_path) != db_hash_before:
            raise AssertionError("data/phocap.db bi thay doi - tu dong khoi phuc.")

        required_router_tokens = [
            'ws.title = "Toàn tỉnh"',
            'ws["A2"] = scope_title',
            'XÁC NHẬN CỦA SỞ GIÁO DỤC VÀ ĐÀO TẠO',
            'ws["J46"] = "GIÁM ĐỐC"',
        ]
        for token in required_router_tokens:
            if token not in new_router_text:
                raise AssertionError(f"Thieu noi dung V2: {token}")

        new_html = html_path.read_text(encoding="utf-8-sig")
        if "{% if selected_report_type == 'PCGD_TH_M1_2025' %}" not in new_html:
            raise AssertionError("Dieu kien nut xuat TH-M1 chua dung selected_report_type.")
        if "Xuất biểu TH-M1 Excel" not in new_html:
            raise AssertionError("Chua co nhan nut Xuat bieu TH-M1 Excel.")

        print("Route cu: KHONG DOI")
        print("app/main.py: KHONG DOI")
        print("data/phocap.db: KHONG DOI")
        print("Luong nghiep vu: KHONG DOI")
        print("Chuc nang cu: GIU NGUYEN")
        print("TH-M1 cap tinh: DA DOI TEN SHEET THANH 'Toan tinh'")
        print("Nut xuat: DA DOI THANH 'Xuat bieu TH-M1 Excel'")

        print("\n" + "=" * 78)
        print("NANG CAP BAI 13C-1 TH-M1 V2 TOAN TINH THANH CONG")
        print("=" * 78)
        print("Ban sao an toan:", backup)
        return 0

    except Exception as exc:
        print("\nCAI DAT KHONG THANH CONG:")
        print(exc)
        traceback.print_exc()
        print("\nDANG KHOI PHUC TRANG THAI TRUOC V2...")
        for rel in reversed(changed):
            saved = backup / rel
            current = project / rel
            if saved.exists():
                copy_with_parent(saved, current)
        print("DA KHOI PHUC TRANG THAI TRUOC V2.")
        print("Ban sao an toan:", backup)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
