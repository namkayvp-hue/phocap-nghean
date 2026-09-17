from __future__ import annotations
import os, re, shutil, traceback
from datetime import datetime
from pathlib import Path

PROJECT = Path(os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")).resolve()
APP = PROJECT / "app"
MENU = APP / "templates" / "partials" / "dropdown_menu_v1.html"
STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = PROJECT / "exports" / f"backup_sua_menu_bao_cao_giao_vien_v1_{STAMP}"
BACKUP_MENU = BACKUP / "app" / "templates" / "partials" / "dropdown_menu_v1.html"
PATCH_MARKER = "FIX_GIAO_VIEN_REPORT_BY_SCHOOL_LEVEL_V1"

RULES = {
    "FIX_CAP_TRUONG_V1_REPORT_MN": "menu_role not in ['TRUONG', 'GIAO_VIEN'] or menu_school_mn or (not menu_school_th and not menu_school_thcs)",
    "FIX_CAP_TRUONG_V1_REPORT_TH": "menu_role not in ['TRUONG', 'GIAO_VIEN'] or menu_school_th or menu_school_liencap",
    "FIX_CAP_TRUONG_V1_REPORT_THCS": "menu_role not in ['TRUONG', 'GIAO_VIEN'] or menu_school_thcs or menu_school_liencap",
    "FIX_CAP_TRUONG_V1_REPORT_XMC": "menu_role not in ['TRUONG', 'GIAO_VIEN']",
}

def read_text(p):
    if not p.exists():
        raise RuntimeError(f"Không tìm thấy: {p}")
    return p.read_text(encoding="utf-8-sig")

def backup():
    BACKUP_MENU.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(MENU, BACKUP_MENU)

def restore():
    if BACKUP_MENU.exists():
        shutil.copy2(BACKUP_MENU, MENU)

def clear_cache():
    for p in APP.rglob("__pycache__"):
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)

def replace_condition(text, marker, condition):
    sm = f"{{# === {marker}_START === #}}"
    em = f"{{# === {marker}_END === #}}"
    s = text.find(sm)
    e = text.find(em, s + len(sm)) if s >= 0 else -1
    if s < 0 or e < 0:
        raise RuntimeError(f"Thiếu khối {marker}")
    block = text[s:e+len(em)]
    m = re.search(r"{%\s*if\s+.+?\s*%}", block)
    if not m:
        raise RuntimeError(f"Không tìm thấy điều kiện trong {marker}")
    new_if = "{% if " + condition + " %}"
    block = block[:m.start()] + new_if + block[m.end():]
    return text[:s] + block + text[e+len(em):]

def patch(text):
    if PATCH_MARKER in text:
        print("Bản sửa này đã có sẵn.")
        return text
    required = [
        "FIX_CAP_TRUONG_V1_SCHOOL_LEVEL_START",
        "FIX_CAP_TRUONG_V1_REPORT_MN_START",
        "FIX_CAP_TRUONG_V1_REPORT_TH_START",
        "FIX_CAP_TRUONG_V1_REPORT_THCS_START",
        "FIX_CAP_TRUONG_V1_REPORT_XMC_START",
    ]
    for x in required:
        if x not in text:
            raise RuntimeError(f"Thiếu marker nền: {x}")
    for marker, cond in RULES.items():
        text = replace_condition(text, marker, cond)
    anchor = "{# === FIX_CAP_TRUONG_V1_REPORT_XMC_END === #}"
    if anchor not in text:
        raise RuntimeError("Thiếu điểm chèn marker cuối.")
    text = text.replace(
        anchor,
        anchor + "\n                    {# === " + PATCH_MARKER + " === #}",
        1
    )
    return text

def verify(text):
    if PATCH_MARKER not in text:
        raise RuntimeError("Chưa có marker xác nhận.")
    norm = " ".join(text.split())
    checks = [
        "menu_role not in ['TRUONG', 'GIAO_VIEN'] or menu_school_mn",
        "menu_role not in ['TRUONG', 'GIAO_VIEN'] or menu_school_th or menu_school_liencap",
        "menu_role not in ['TRUONG', 'GIAO_VIEN'] or menu_school_thcs or menu_school_liencap",
    ]
    for c in checks:
        if " ".join(c.split()) not in norm:
            raise RuntimeError(f"Kiểm tra chưa đạt: {c}")
    from jinja2 import Environment, FileSystemLoader
    Environment(loader=FileSystemLoader(str(APP/"templates"))).get_template("partials/dropdown_menu_v1.html")

def main():
    print("="*96)
    print("SỬA MENU BÁO CÁO CẤP GIÁO VIÊN V1")
    print("="*96)
    print("Giáo viên chỉ thấy báo cáo đúng cấp học của trường.")
    print("Giữ nguyên 5.1 Trung tâm báo cáo.")
    print("Không đổi database, dữ liệu, điều tra hộ dân, Đội ngũ, CSVC.")
    before = read_text(MENU)
    backup()
    try:
        after = patch(before)
        MENU.write_text(after, encoding="utf-8")
        verify(read_text(MENU))
        clear_cache()
        print("")
        print("CÀI ĐẶT THÀNH CÔNG.")
        print("Backup:", BACKUP)
        print("Khởi động lại Uvicorn, đăng nhập lại Giáo viên và nhấn Ctrl + F5.")
        return 0
    except Exception:
        traceback.print_exc()
        print("")
        print("CÓ LỖI - ĐANG KHÔI PHỤC...")
        restore()
        clear_cache()
        print("ĐÃ KHÔI PHỤC SOURCE.")
        print("Backup:", BACKUP)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
