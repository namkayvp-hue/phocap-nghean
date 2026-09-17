from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
import traceback
from datetime import datetime
from pathlib import Path

PROJECT = Path(r"C:\PhoCap")
VERSION = "MENU-SO-XUONG-V1.1"
CSS_START = "/* === MENU SO XUONG V1: BAT DAU === */"
CSS_END = "/* === MENU SO XUONG V1: KET THUC === */"
INLINE_START = "<!-- === MENU SO XUONG V1.1 STYLE: BAT DAU === -->"
INLINE_END = "<!-- === MENU SO XUONG V1.1 STYLE: KET THUC === -->"

# CSS dự phòng chỉ dùng khi khối CSS V1 không còn trong style.css.
FALLBACK_CSS = r'''
.pc-global-nav {
    position: sticky;
    top: 0;
    z-index: 5000;
    width: 100%;
    font-family: Arial, Helvetica, sans-serif;
    color: #ffffff;
    background: #ffffff;
    box-shadow: 0 3px 12px rgba(18, 52, 86, 0.18);
}

.pc-global-nav, .pc-global-nav * {
    box-sizing: border-box;
}

.pc-global-nav__top {
    min-height: 56px;
    padding: 7px max(18px, calc((100% - 1280px) / 2));
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 18px;
    background: linear-gradient(90deg, #0d47a1 0%, #1565c0 58%, #1976d2 100%);
}

.pc-global-nav__brand {
    min-width: 0;
    display: inline-flex;
    align-items: center;
    gap: 10px;
    color: #ffffff !important;
    text-decoration: none !important;
}

.pc-global-nav__brand-mark {
    width: 36px;
    height: 36px;
    flex: 0 0 36px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border-radius: 8px;
    background: #ffffff;
    color: #0d47a1;
    font-size: 14px;
    font-weight: 800;
}

.pc-global-nav__brand-text {
    min-width: 0;
    display: flex;
    flex-direction: column;
    line-height: 1.15;
}

.pc-global-nav__brand-text strong {
    color: #ffffff;
    font-size: 14px;
    letter-spacing: .25px;
    white-space: nowrap;
}

.pc-global-nav__brand-text small {
    margin-top: 3px;
    color: rgba(255,255,255,.9);
    font-size: 11px;
}

.pc-global-nav__account {
    display: grid;
    grid-template-columns: minmax(0, auto) auto;
    grid-template-areas: "name logout" "unit logout";
    align-items: center;
    column-gap: 12px;
    text-align: right;
}

.pc-global-nav__account-name {
    grid-area: name;
    color: #ffffff;
    font-size: 14px;
    font-weight: 700;
}

.pc-global-nav__account-unit {
    grid-area: unit;
    max-width: 460px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    color: rgba(255,255,255,.9);
    font-size: 11px;
}

.pc-global-nav__logout-form {
    grid-area: logout;
    margin: 0 !important;
}

.pc-global-nav__logout {
    min-height: 34px;
    padding: 7px 12px;
    border: 1px solid rgba(255,255,255,.62);
    border-radius: 7px;
    background: rgba(255,255,255,.12);
    color: #ffffff;
    font: inherit;
    font-size: 12px;
    font-weight: 700;
    cursor: pointer;
}

.pc-global-nav__logout:hover,
.pc-global-nav__logout:focus-visible {
    background: #ffffff;
    color: #0d47a1;
    outline: none;
}

.pc-global-nav__bar {
    min-height: 43px;
    padding: 0 max(18px, calc((100% - 1280px) / 2));
    display: flex;
    align-items: stretch;
    gap: 0;
    background: #ffffff;
    border-bottom: 1px solid #d8e1eb;
    color: #25364a;
}

.pc-global-nav__home,
.pc-menu-trigger {
    min-height: 43px;
    margin: 0;
    padding: 0 15px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    border: 0;
    border-right: 1px solid #e5ebf1;
    border-radius: 0;
    background: transparent;
    color: #25364a !important;
    font: inherit;
    font-size: 14px;
    font-weight: 600;
    line-height: 1.2;
    text-decoration: none !important;
    white-space: nowrap;
    cursor: pointer;
    box-shadow: none;
}

.pc-global-nav__home:hover,
.pc-global-nav__home:focus-visible,
.pc-menu-trigger:hover,
.pc-menu-trigger:focus-visible,
.pc-menu-group.is-open > .pc-menu-trigger,
.pc-menu-group.is-active > .pc-menu-trigger,
.pc-global-nav__home.is-active {
    background: #eaf3ff;
    color: #0d5fb8 !important;
    outline: none;
}

.pc-menu-group {
    position: relative;
    display: flex;
    align-items: stretch;
}

.pc-menu-caret {
    font-size: 11px;
    transition: transform .16s ease;
}

.pc-menu-group.is-open .pc-menu-caret {
    transform: rotate(180deg);
}

.pc-dropdown {
    position: absolute;
    top: 100%;
    left: 0;
    z-index: 5100;
    width: max-content;
    min-width: 285px;
    max-width: min(410px, calc(100vw - 28px));
    padding: 7px 0;
    display: none;
    background: #ffffff;
    border: 1px solid #d9e2ec;
    border-radius: 0 0 8px 8px;
    box-shadow: 0 12px 28px rgba(30,53,79,.18);
}

.pc-menu-group.is-open > .pc-dropdown,
.pc-menu-group:focus-within > .pc-dropdown {
    display: block;
}

.pc-dropdown--right {
    left: auto;
    right: 0;
}

.pc-dropdown a {
    min-height: 38px;
    padding: 9px 15px;
    display: flex;
    align-items: center;
    color: #26384d !important;
    font-size: 13px;
    font-weight: 500;
    line-height: 1.35;
    text-decoration: none !important;
    white-space: normal;
}

.pc-dropdown a:hover,
.pc-dropdown a:focus-visible {
    background: #edf5ff;
    color: #0d5fb8 !important;
    outline: none;
}

.pc-dropdown__note {
    margin: 4px 10px;
    padding: 9px 10px;
    display: block;
    border-radius: 6px;
    background: #f5f8fb;
    color: #617286;
    font-size: 12px;
    line-height: 1.45;
}

@media (max-width: 980px) {
    .pc-global-nav__account-unit { max-width: 260px; }
    .pc-global-nav__bar { overflow-x: auto; overflow-y: visible; scrollbar-width: thin; }
    .pc-global-nav__home, .pc-menu-trigger { padding-inline: 12px; }
}

@media (max-width: 680px) {
    .pc-global-nav { position: relative; }
    .pc-global-nav__top { flex-direction: column; align-items: stretch; gap: 8px; }
    .pc-global-nav__brand-text strong { white-space: normal; }
    .pc-global-nav__account { grid-template-columns: 1fr auto; text-align: left; }
    .pc-global-nav__account-unit { max-width: 100%; }
    .pc-global-nav__bar { flex-wrap: wrap; overflow: visible; padding: 4px 8px; }
    .pc-global-nav__home, .pc-menu-trigger { min-height: 40px; border-right: 0; border-radius: 6px; }
    .pc-dropdown, .pc-dropdown--right { position: fixed; top: auto; right: 10px; left: 10px; width: auto; max-width: none; border-radius: 8px; }
}

@media print {
    .pc-global-nav { display: none !important; }
}
'''


def sha256(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def copy_with_parent(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def remove_block(text: str, start: str, end: str) -> str:
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), re.DOTALL)
    return pattern.sub("", text)


def main() -> int:
    project = PROJECT
    if len(sys.argv) >= 2:
        project = Path(sys.argv[1]).expanduser().resolve()

    partial = project / "app" / "templates" / "partials" / "dropdown_menu_v1.html"
    css_path = project / "app" / "static" / "css" / "style.css"
    main_py = project / "app" / "main.py"
    db_path = project / "data" / "phocap.db"

    print("\n" + "=" * 72)
    print("SUA MENU SO XUONG V1.1 - SUA LOI CSS KHONG AP DUNG")
    print("CHI SUA PHAN MENU - KHONG DOI ROUTE - KHONG DOI DU LIEU")
    print("=" * 72)

    for required in [partial, css_path, main_py]:
        if not required.exists():
            raise FileNotFoundError(f"Khong tim thay: {required}")

    partial_text = partial.read_text(encoding="utf-8-sig")
    if "pc-global-nav" not in partial_text:
        raise RuntimeError("Khong nhan dien duoc menu V1 trong dropdown_menu_v1.html")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = project / "exports" / f"backup_menu_so_xuong_v1_1_{stamp}"
    backup.mkdir(parents=True, exist_ok=False)

    main_hash = sha256(main_py)
    db_hash = sha256(db_path)

    print("\nBUOC 1 - SAO LUU AN TOAN")
    for p in [partial, css_path, main_py]:
        copy_with_parent(p, backup / p.relative_to(project))
    if db_path.exists():
        copy_with_parent(db_path, backup / db_path.relative_to(project))
    print(f"Ban sao an toan: {backup}")

    try:
        print("\nBUOC 2 - CHUYEN CSS MENU VAO CHINH MENU DUNG CHUNG")
        css_text = css_path.read_text(encoding="utf-8-sig")
        match = re.search(
            re.escape(CSS_START) + r"(.*?)" + re.escape(CSS_END),
            css_text,
            flags=re.DOTALL,
        )
        if match:
            css_body = match.group(1).strip()
            # Bổ sung reset cục bộ để tránh CSS từng trang ghi đè menu.
            css_body = (
                ".pc-global-nav, .pc-global-nav * { box-sizing: border-box; }\n"
                + css_body
                + "\n.pc-global-nav a { text-decoration: none; }\n"
            )
        else:
            css_body = FALLBACK_CSS.strip()

        # V1.1 tự chứa CSS trong partial để mọi giao diện đều nhận được,
        # kể cả các trang có CSS riêng hoặc bộ nhớ đệm stylesheet khác nhau.
        partial_clean = remove_block(partial_text, INLINE_START, INLINE_END).lstrip()
        inline = (
            INLINE_START
            + "\n<style id=\"pc-menu-v1-inline-style\">\n"
            + css_body
            + "\n</style>\n"
            + INLINE_END
            + "\n"
        )
        partial.write_text(inline + partial_clean, encoding="utf-8")
        print("Da cap nhat: app/templates/partials/dropdown_menu_v1.html")

        print("\nBUOC 3 - GO BO KHOI CSS MENU V1 KHOI STYLE.CSS")
        # Menu nay da tu mang CSS, nen xoa khoi V1 cu de tranh lech cache/ghi de.
        cleaned_css = re.sub(
            re.escape(CSS_START) + r".*?" + re.escape(CSS_END),
            "",
            css_text,
            flags=re.DOTALL,
        ).rstrip() + "\n"
        css_path.write_text(cleaned_css, encoding="utf-8")
        print("Da lam sach khoi CSS V1 cu trong app/static/css/style.css")

        print("\nBUOC 4 - KIEM TRA JINJA VA AN TOAN")
        from jinja2 import Environment, FileSystemLoader

        templates_dir = project / "app" / "templates"
        env = Environment(loader=FileSystemLoader(str(templates_dir)))
        env.get_template("partials/dropdown_menu_v1.html")

        final_partial = partial.read_text(encoding="utf-8-sig")
        if INLINE_START not in final_partial or "pc-menu-v1-inline-style" not in final_partial:
            raise RuntimeError("CSS noi bo V1.1 chua duoc chen dung")
        if ".pc-dropdown" not in final_partial or "display: none" not in final_partial:
            raise RuntimeError("Thieu quy tac an menu so xuong")
        if CSS_START in css_path.read_text(encoding="utf-8-sig"):
            raise RuntimeError("Khoi CSS V1 cu van con trong style.css")
        if sha256(main_py) != main_hash:
            raise RuntimeError("app/main.py da bi thay doi - dung cai dat")
        if sha256(db_path) != db_hash:
            raise RuntimeError("data/phocap.db da bi thay doi - dung cai dat")

        manifest = {
            "version": VERSION,
            "installed_at": datetime.now().isoformat(timespec="seconds"),
            "backup": str(backup),
            "changed_files": [
                "app/templates/partials/dropdown_menu_v1.html",
                "app/static/css/style.css",
            ],
            "main_py_sha256": main_hash,
            "database_sha256": db_hash,
        }
        (backup / "MENU_V1_1_MANIFEST.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (project / "exports" / "menu_so_xuong_v1_1_backup_moi_nhat.txt").write_text(
            str(backup), encoding="utf-8"
        )

        print("Jinja: DAT")
        print("app/main.py: KHONG DOI")
        print("data/phocap.db: KHONG DOI")
        print("CSS menu: TU CHUA TRONG PARTIAL - KHONG PHU THUOC CACHE STYLE.CSS")
        print("\n" + "=" * 72)
        print("SUA MENU SO XUONG V1.1 THANH CONG")
        print("=" * 72)
        print(f"Ban sao an toan: {backup}")
        return 0

    except Exception:
        print("\nSUA KHONG THANH CONG - DANG KHOI PHUC 2 TEP GIAO DIEN...")
        traceback.print_exc()
        for p in [partial, css_path]:
            saved = backup / p.relative_to(project)
            if saved.exists():
                copy_with_parent(saved, p)
        print("DA KHOI PHUC MENU/CSS CU.")
        print("app/main.py va data/phocap.db KHONG BI GHI DE.")
        print(f"Ban sao an toan: {backup}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
