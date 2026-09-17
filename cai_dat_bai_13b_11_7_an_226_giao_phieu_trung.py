from __future__ import annotations
import os, re, shutil, subprocess, sys, traceback
from datetime import datetime
from pathlib import Path

PROJECT = Path(os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")).resolve()
APP = PROJECT / "app"
MENU = APP / "templates" / "partials" / "dropdown_menu_v1.html"
STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = PROJECT / "exports" / f"backup_source_bai_13b_11_7_{STAMP}"

MARK_XA = "BAI_13B_11_7_HIDE_226_XA"
MARK_TRUONG = "BAI_13B_11_7_HIDE_226_TRUONG"

def read_text(p):
    if not p.exists():
        raise RuntimeError(f"Không tìm thấy: {p}")
    return p.read_text(encoding="utf-8-sig")

def write_text(p, s):
    p.write_text(s, encoding="utf-8")

def backup():
    dst = BACKUP / MENU.relative_to(PROJECT)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(MENU, dst)

def restore():
    src = BACKUP / MENU.relative_to(PROJECT)
    if src.exists():
        shutil.copy2(src, MENU)

def clear_cache():
    for p in APP.rglob("__pycache__"):
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)

def hide_exact_link(text, href_fragment, label, marker):
    if marker in text:
        return text

    pattern = re.compile(
        r'(?P<indent>[ \t]*)<a href="/dieu-tra"\s+'
        r'data-batch-template="(?P<tpl>[^"]*' + re.escape(href_fragment) + r')" '
        r'role="menuitem">' + re.escape(label) + r'</a>'
    )
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        raise RuntimeError(
            f"Không tìm thấy đúng 1 mục '{label}'. Tìm thấy: {len(matches)}"
        )

    m = matches[0]
    indent = m.group("indent")
    original = m.group(0)
    replacement = (
        f"{indent}{{# === {marker}_START === #}}\n"
        f"{indent}{{# Ẩn khỏi menu vì thao tác đã có trên màn hình danh sách hộ; "
        f"không xóa route/backend. #}}\n"
        f"{indent}{{#\n{original}\n{indent}#}}\n"
        f"{indent}{{# === {marker}_END === #}}"
    )
    return text[:m.start()] + replacement + text[m.end():]

def patch(text):
    text = hide_exact_link(
        text,
        "/giao-phieu-truong",
        "2.2.6. Giao phiếu cho trường",
        MARK_XA,
    )
    text = hide_exact_link(
        text,
        "/giao-phieu-giao-vien",
        "2.2.6. Giao phiếu cho giáo viên",
        MARK_TRUONG,
    )
    return text

def verify():
    text = read_text(MENU)
    for marker in (
        MARK_XA + "_START", MARK_XA + "_END",
        MARK_TRUONG + "_START", MARK_TRUONG + "_END",
        "2.2.1. Danh sách hộ dân / phiếu được giao",
        "2.2.4. Nhập Excel cập nhật hộ dân",
        "2.2.5. Trường tham gia và khóa/mở trường",
        "2.2.7. GV trường gửi về xã/phường",
        "2.2.5. Nhiệm vụ trường / gửi kết quả lên xã",
    ):
        if marker not in text:
            raise RuntimeError(f"Kiểm tra sau cài không đạt, thiếu: {marker}")

    if "/giao-phieu-truong" not in text or "/giao-phieu-giao-vien" not in text:
        raise RuntimeError("Route menu bị xóa khỏi source thay vì chỉ ẩn.")

    code = (
        "from pathlib import Path\n"
        "from jinja2 import Environment, FileSystemLoader\n"
        "p=Path(r'C:\\\\PhoCap')\n"
        "e=Environment(loader=FileSystemLoader(str(p/'app'/'templates')))\n"
        "e.get_template('partials/dropdown_menu_v1.html')\n"
        "print('JINJA_TEMPLATE=OK')\n"
    )
    r = subprocess.run(
        [sys.executable, "-c", code],
        cwd=PROJECT, text=True, capture_output=True
    )
    if r.stdout:
        print(r.stdout.rstrip())
    if r.stderr:
        print(r.stderr.rstrip())
    if r.returncode != 0:
        raise RuntimeError("Jinja template kiểm tra không đạt.")

def main():
    print("=" * 108)
    print("BÀI 13B-11.7 - ẨN MỤC 2.2.6 GIAO PHIẾU BỊ TRÙNG")
    print("=" * 108)
    print()
    print("SẼ ẨN:")
    print(" - Cấp Xã: 2.2.6. Giao phiếu cho trường.")
    print(" - Cấp Trường: 2.2.6. Giao phiếu cho giáo viên.")
    print()
    print("GIỮ NGUYÊN:")
    print(" - Nút giao phiếu trên màn hình danh sách hộ.")
    print(" - Route/backend.")
    print(" - Các mục 2.2 khác.")
    print(" - Database và phân quyền backend.")
    print()

    BACKUP.mkdir(parents=True, exist_ok=False)
    backup()
    print("Backup source:", BACKUP)

    try:
        before = read_text(MENU)
        write_text(MENU, patch(before))
        verify()
        clear_cache()
        print()
        print("KIỂM TRA SAU CÀI:")
        print(" - Ẩn 2.2.6 cấp Xã: OK")
        print(" - Ẩn 2.2.6 cấp Trường: OK")
        print(" - Route/backend vẫn giữ: OK")
        print(" - Các mục 2.2 khác vẫn giữ: OK")
        print(" - Jinja template: OK")
        print(" - Database: KHÔNG THAY ĐỔI")
        print()
        print("CÀI ĐẶT BÀI 13B-11.7 THÀNH CÔNG")
        return 0
    except Exception:
        traceback.print_exc()
        print()
        print("CÓ LỖI - ĐANG KHÔI PHỤC MENU...")
        restore()
        clear_cache()
        print("ĐÃ KHÔI PHỤC SOURCE.")
        print("Database không bị thay đổi.")
        print("Backup source:", BACKUP)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
