# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(r"C:\PhoCap")
DB = ROOT / "data" / "phocap.db"
MENU = ROOT / "app" / "templates" / "partials" / "dropdown_menu_v1.html"
BACKUP_DIR = ROOT / "backups"
EXPORT_DIR = ROOT / "exports"
OUT = EXPORT_DIR / "BATCH_THEM_MENU_MANG_LUOI_HIEN_HANH_18B.txt"

EXPECTED_DB_SHA = "2a43e36ff8f192abb46668faa1366ed7242984bfd876f90572cd83b90ee7837e"

MARKER_START = "<!-- === BATCH18B_NETWORK_MENU_START === -->"
MARKER_END = "<!-- === BATCH18B_NETWORK_MENU_END === -->"

PATCH = '<!-- === BATCH18B_NETWORK_MENU_START === -->\n<script>\ndocument.addEventListener("DOMContentLoaded", function () {\n    try {\n        if (document.querySelector(\'a[href="/mang-luoi-hien-hanh"]\')) {\n            return;\n        }\n\n        const nodes = Array.from(\n            document.querySelectorAll("a,button,span,summary,div")\n        );\n\n        const label = nodes.find(function (el) {\n            const text = (el.textContent || "").replace(/\\s+/g, " ").trim();\n            return text === "1. Danh mục" || text.startsWith("1. Danh mục");\n        });\n\n        if (!label) {\n            return;\n        }\n\n        let parent = label.closest("li, details, .dropdown, .menu-item, .nav-item, div");\n        if (!parent) {\n            return;\n        }\n\n        let submenu = parent.querySelector(\n            "ul, .dropdown-menu, .submenu, .menu-dropdown, .dropdown-content"\n        );\n\n        if (!submenu) {\n            const next = parent.nextElementSibling;\n            if (\n                next &&\n                (\n                    next.matches("ul") ||\n                    next.classList.contains("dropdown-menu") ||\n                    next.classList.contains("submenu") ||\n                    next.classList.contains("menu-dropdown") ||\n                    next.classList.contains("dropdown-content")\n                )\n            ) {\n                submenu = next;\n            }\n        }\n\n        if (!submenu) {\n            return;\n        }\n\n        const existingLink = submenu.querySelector("a");\n        if (!existingLink) {\n            return;\n        }\n\n        let newNode;\n        const directChild = existingLink.parentElement;\n\n        if (\n            directChild &&\n            directChild !== submenu &&\n            directChild.parentElement === submenu\n        ) {\n            newNode = directChild.cloneNode(true);\n            const a = newNode.querySelector("a");\n            if (!a) return;\n            a.href = "/mang-luoi-hien-hanh";\n            a.textContent = "Mạng lưới năm học hiện hành";\n            a.classList.remove("active");\n            a.removeAttribute("aria-current");\n        } else {\n            newNode = existingLink.cloneNode(true);\n            newNode.href = "/mang-luoi-hien-hanh";\n            newNode.textContent = "Mạng lưới năm học hiện hành";\n            newNode.classList.remove("active");\n            newNode.removeAttribute("aria-current");\n        }\n\n        submenu.appendChild(newNode);\n    } catch (err) {\n        console.error("Không thể gắn menu Mạng lưới năm học hiện hành:", err);\n    }\n});\n</script>\n<!-- === BATCH18B_NETWORK_MENU_END === -->'

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()

def log(f, *parts):
    s = " ".join(str(x) for x in parts)
    print(s)
    f.write(s + "\n")
    f.flush()

def main():
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    with OUT.open("w", encoding="utf-8-sig", newline="\n") as f:
        log(f, "=" * 150)
        log(f, "BATCH 18B - THÊM MENU 'MẠNG LƯỚI NĂM HỌC HIỆN HÀNH'")
        log(f, "VỊ TRÍ: 1. DANH MỤC -> MẠNG LƯỚI NĂM HỌC HIỆN HÀNH")
        log(f, "CHỈ SỬA TEMPLATE MENU; KHÔNG GHI DATABASE")
        log(f, "=" * 150)

        db_sha = sha256_file(DB)
        log(f, "DB_SHA_BEFORE =", db_sha)
        log(f, "EXPECTED_DB_SHA =", EXPECTED_DB_SHA)
        if db_sha != EXPECTED_DB_SHA:
            raise RuntimeError("DB SHA khác nền Batch 18/18A.")

        con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True, timeout=30)
        try:
            integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
            fk = con.execute("PRAGMA foreign_key_check").fetchall()
        finally:
            con.close()

        log(f, "INTEGRITY =", integrity)
        log(f, "FK =", len(fk))
        if integrity != "ok" or fk:
            raise RuntimeError("Database health không đạt.")

        if not MENU.exists():
            raise RuntimeError("Không tìm thấy app\\templates\\partials\\dropdown_menu_v1.html")

        text = MENU.read_text(encoding="utf-8")
        log(f, "MENU_SHA_BEFORE =", sha256_file(MENU))

        if "1. Danh mục" not in text:
            raise RuntimeError("Không tìm thấy nhãn '1. Danh mục' trong menu hiện tại.")

        if MARKER_START in text and MARKER_END in text:
            log(f, "PATCH_STATUS = ALREADY_PRESENT")
        else:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup = BACKUP_DIR / f"dropdown_menu_v1_truoc_18B_{ts}.html"
            shutil.copy2(MENU, backup)
            log(f, "SOURCE_BACKUP =", backup)

            MENU.write_text(text.rstrip() + "\n\n" + PATCH + "\n", encoding="utf-8")
            log(f, "PATCH_STATUS = ADDED")

        after = MENU.read_text(encoding="utf-8")
        required = [
            MARKER_START,
            "/mang-luoi-hien-hanh",
            "Mạng lưới năm học hiện hành",
            MARKER_END,
        ]
        missing = [x for x in required if x not in after]
        if missing:
            raise RuntimeError(f"Menu patch thiếu thành phần bắt buộc: {missing}")

        log(f, "MENU_SHA_AFTER =", sha256_file(MENU))
        log(f, "DB_SHA_AFTER =", sha256_file(DB))
        log(f, "DATABASE_WRITES_THIS_RUN = 0")
        log(f, "BATCH_18B_SUCCESS = YES")
        log(f, "NEXT = Khởi động lại Uvicorn hoặc tải lại trang; mở 1. Danh mục và chọn 'Mạng lưới năm học hiện hành'.")
        log(f, "=" * 150)

    return 0

if __name__ == "__main__":
    try:
        rc = main()
    except Exception as exc:
        try:
            EXPORT_DIR.mkdir(parents=True, exist_ok=True)
            with OUT.open("a", encoding="utf-8-sig", newline="\n") as f:
                log(f, "")
                log(f, "=" * 150)
                log(f, "BATCH_18B_SUCCESS = NO")
                log(f, "ERROR =", repr(exc))
                if DB.exists():
                    log(f, "DB_SHA_CURRENT =", sha256_file(DB))
                log(f, "DỪNG AN TOÀN.")
                log(f, "=" * 150)
        except Exception:
            print("ERROR =", repr(exc))
        rc = 1

    sys.exit(rc)
