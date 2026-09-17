from __future__ import annotations

import json
import shutil
import traceback
from datetime import datetime
from pathlib import Path

PROJECT = Path(r"C:\PhoCap").resolve()
HOME = PROJECT / "app" / "templates" / "index.html"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = PROJECT / "exports" / f"backup_giao_vien_mobile_v1_8a_{STAMP}"
MANIFEST = BACKUP / "manifest.json"

START = "{# === GV_MOBILE_V18A_ROOT_REDIRECT_START === #}"
END = "{# === GV_MOBILE_V18A_ROOT_REDIRECT_END === #}"

BLOCK = "{# === GV_MOBILE_V18A_ROOT_REDIRECT_START === #}\n{% if nguoi_dung.role_code == 'GIAO_VIEN' %}\n<style>\n@media (max-width: 760px) {\n    html, body {\n        background: #f3f6fa !important;\n    }\n\n    body {\n        visibility: hidden;\n    }\n}\n</style>\n\n<script>\n(function () {\n    if (window.matchMedia && window.matchMedia('(max-width: 760px)').matches) {\n        window.location.replace('/dieu-tra');\n    }\n})();\n</script>\n{% endif %}\n{# === GV_MOBILE_V18A_ROOT_REDIRECT_END === #}\n"

def strip_block(text: str) -> str:
    while START in text and END in text:
        a = text.index(START)
        b = text.index(END, a) + len(END)
        text = text[:a] + text[b:]
    return text

def main():
    print("=" * 78)
    print("GIAO VIEN MOBILE V1.8A")
    print("SUA MAN HINH TRANG CHU DIEN THOAI CUA GIAO VIEN")
    print("TRANG CHU -> TU DONG VAO /dieu-tra")
    print("TAI /dieu-tra CHI CON: CHON NAM + PHIEU PHAN CONG")
    print("=" * 78)

    if not HOME.exists():
        raise RuntimeError(f"Khong tim thay: {HOME}")

    BACKUP.mkdir(parents=True, exist_ok=False)
    backup_home = BACKUP / "app" / "templates" / "index.html"
    backup_home.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(HOME, backup_home)

    MANIFEST.write_text(
        json.dumps(
            {
                "file": "app/templates/index.html",
                "backup": str(backup_home),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    try:
        text = HOME.read_text(encoding="utf-8-sig")
        text = strip_block(text)

        anchor = "<body>"
        if anchor not in text:
            raise RuntimeError("Khong tim thay the <body> trong app/templates/index.html")

        text = text.replace(anchor, anchor + "\n" + BLOCK, 1)
        HOME.write_text(text, encoding="utf-8")

        check = HOME.read_text(encoding="utf-8")
        if START not in check or "window.location.replace('/dieu-tra')" not in check:
            raise RuntimeError("Kiem tra sau cai dat khong dat.")

        print("")
        print("KET QUA:")
        print(" - Tai khoan GIAO_VIEN tren dien thoai mo Trang chu: tu dong vao /dieu-tra")
        print(" - Man hinh /dieu-tra V1.8: Chon nam + Phieu phan cong")
        print(" - May tinh/desktop: giu nguyen")
        print(" - Database: khong thay doi")
        print(" - Router Python: khong thay doi")
        print("")
        print("CAI DAT GIAO VIEN MOBILE V1.8A THANH CONG")
        print("Backup:", BACKUP)
        return 0

    except Exception:
        traceback.print_exc()
        if backup_home.exists():
            shutil.copy2(backup_home, HOME)
        print("")
        print("CO LOI - DA KHOI PHUC index.html TU DONG.")
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
