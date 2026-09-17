# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import re
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
OUT = EXPORT_DIR / "BATCH_SUA_MENU_MANG_LUOI_HIEN_HANH_18C.txt"

EXPECTED_DB_SHA = "2a43e36ff8f192abb46668faa1366ed7242984bfd876f90572cd83b90ee7837e"

LINK_TEXT = "1.3.4. Mạng lưới năm học hiện hành"
LINK_HREF = "/mang-luoi-hien-hanh"
MARKER = "<!-- BATCH18C_NETWORK_CURRENT_MENU -->"


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


def validate_db():
    sha = sha256_file(DB)
    if sha != EXPECTED_DB_SHA:
        raise RuntimeError("DB SHA khác nền sau Batch 18B.")
    con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True, timeout=30)
    try:
        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
        fk = con.execute("PRAGMA foreign_key_check").fetchall()
    finally:
        con.close()
    if integrity != "ok" or fk:
        raise RuntimeError(f"Database health không đạt: integrity={integrity}, fk={len(fk)}")
    return sha, integrity, len(fk)


def build_link_from_anchor(anchor_html: str) -> str:
    new_anchor = anchor_html

    # Thay href.
    new_anchor, n_href = re.subn(
        r'href\s*=\s*(["\']).*?\1',
        f'href="{LINK_HREF}"',
        new_anchor,
        count=1,
        flags=re.I | re.S,
    )
    if n_href != 1:
        raise RuntimeError("Không thay được href của mục mẫu.")

    # Thay phần text nằm giữa thẻ <a>...</a>, giữ các thẻ con nếu có là quá rủi ro.
    # Menu hiện tại của người dùng hiển thị text trực tiếp nên dùng text sạch.
    m = re.match(r'(?is)(<a\b[^>]*>)(.*?)(</a>)', new_anchor.strip())
    if not m:
        raise RuntimeError("Không phân tích được anchor mẫu.")
    return f'{m.group(1)}{LINK_TEXT}{m.group(3)}'


def patch_menu(text: str):
    # Nếu đã có route thật thì không chèn thêm.
    if LINK_HREF in text and LINK_TEXT in text:
        return text, "ALREADY_PRESENT"

    # 1) Ưu tiên clone đúng anchor "1.3.3. Đổi tên trường".
    patterns = [
        r'(?is)<a\b[^>]*>.*?1\.3\.3\.\s*Đổi tên trường.*?</a>',
        r'(?is)<a\b[^>]*>.*?Đổi tên trường.*?</a>',
    ]
    anchor_match = None
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            anchor_match = m
            break

    if anchor_match:
        anchor = anchor_match.group(0)
        new_anchor = build_link_from_anchor(anchor)

        # Nếu anchor nằm trong <li>...</li>, clone cả LI để giữ cấu trúc/CSS.
        before = text[:anchor_match.start()]
        after = text[anchor_match.end():]

        li_open = before.lower().rfind("<li")
        li_close_before = before.lower().rfind("</li>")
        next_li_close = after.lower().find("</li>")

        if li_open > li_close_before and next_li_close >= 0:
            li_end = anchor_match.end() + next_li_close + len("</li>")
            li_html = text[li_open:li_end]
            new_li = li_html.replace(anchor, new_anchor, 1)
            patched = text[:li_end] + "\n" + MARKER + "\n" + new_li + text[li_end:]
            return patched, "CLONED_LI_AFTER_1_3_3"

        # Không có LI: chèn anchor sibling ngay sau anchor mẫu.
        insert_at = anchor_match.end()
        patched = text[:insert_at] + "\n" + MARKER + "\n" + new_anchor + text[insert_at:]
        return patched, "CLONED_ANCHOR_AFTER_1_3_3"

    # 2) Fallback: tìm đóng submenu gần "1.3. Công cụ dữ liệu" và chèn link đơn giản.
    idx = text.find("1.3. Công cụ dữ liệu")
    if idx < 0:
        idx = text.find("1.3. Công cụ")
    if idx < 0:
        raise RuntimeError("Không tìm thấy khu vực 1.3. Công cụ dữ liệu.")

    tail = text[idx: idx + 12000]
    # Tìm một href trong submenu để lấy class.
    m = re.search(r'(?is)<a\b([^>]*)href\s*=\s*(["\']).*?\2([^>]*)>.*?</a>', tail)
    if not m:
        raise RuntimeError("Không tìm thấy anchor mẫu trong submenu Công cụ dữ liệu.")

    sample_full = m.group(0)
    new_anchor = build_link_from_anchor(sample_full)

    # Tìm ngay sau "Đổi tên trường" trong tail nếu có.
    pos_local = tail.find("Đổi tên trường")
    if pos_local >= 0:
        close_a = tail.find("</a>", pos_local)
        if close_a >= 0:
            insert_at = idx + close_a + len("</a>")
            patched = text[:insert_at] + "\n" + MARKER + "\n" + new_anchor + text[insert_at:]
            return patched, "FALLBACK_AFTER_RENAME_TEXT"

    raise RuntimeError("Không xác định được vị trí chèn an toàn.")


def main():
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    with OUT.open("w", encoding="utf-8-sig", newline="\n") as f:
        log(f, "=" * 150)
        log(f, "BATCH 18C - SỬA MENU MẠNG LƯỚI NĂM HỌC HIỆN HÀNH")
        log(f, "CHÈN TRỰC TIẾP 1.3.4 SAU '1.3.3. ĐỔI TÊN TRƯỜNG'")
        log(f, "KHÔNG DÙNG JAVASCRIPT ĐỘNG; KHÔNG GHI DATABASE")
        log(f, "=" * 150)

        db_sha, integrity, fk_count = validate_db()
        log(f, "DB_SHA =", db_sha)
        log(f, "INTEGRITY =", integrity)
        log(f, "FK =", fk_count)

        if not MENU.exists():
            raise RuntimeError("Không tìm thấy dropdown_menu_v1.html")

        before = MENU.read_text(encoding="utf-8")
        before_sha = sha256_file(MENU)
        log(f, "MENU_SHA_BEFORE =", before_sha)

        patched, mode = patch_menu(before)
        log(f, "PATCH_MODE =", mode)

        if patched != before:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup = BACKUP_DIR / f"dropdown_menu_v1_truoc_18C_{ts}.html"
            shutil.copy2(MENU, backup)
            log(f, "SOURCE_BACKUP =", backup)

            MENU.write_text(patched, encoding="utf-8")

        after = MENU.read_text(encoding="utf-8")
        if LINK_HREF not in after:
            raise RuntimeError("Sau patch không có route /mang-luoi-hien-hanh.")
        if LINK_TEXT not in after:
            raise RuntimeError("Sau patch không có nhãn menu 1.3.4.")

        log(f, "MENU_SHA_AFTER =", sha256_file(MENU))
        log(f, "DB_SHA_AFTER =", sha256_file(DB))
        log(f, "DATABASE_WRITES_THIS_RUN = 0")
        log(f, "BATCH_18C_SUCCESS = YES")
        log(f, "EXPECTED_UI = 1. Danh mục -> 1.3. Công cụ dữ liệu -> 1.3.4. Mạng lưới năm học hiện hành")
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
                log(f, "BATCH_18C_SUCCESS = NO")
                log(f, "ERROR =", repr(exc))
                if DB.exists():
                    log(f, "DB_SHA_CURRENT =", sha256_file(DB))
                log(f, "DỪNG AN TOÀN.")
                log(f, "=" * 150)
        except Exception:
            print("ERROR =", repr(exc))
        rc = 1
    sys.exit(rc)
