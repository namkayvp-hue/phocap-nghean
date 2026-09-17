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
VERSION = "MENU-SO-XUONG-V1"
INCLUDE_MARKER = '{% include "partials/dropdown_menu_v1.html" %}'
CSS_START = "/* === MENU SO XUONG V1: BAT DAU === */"
CSS_END = "/* === MENU SO XUONG V1: KET THUC === */"

EXCLUDED_TEMPLATES = {
    "auth/login.html",
    "surveys/field_print.html",
}

MENU_TEMPLATE = r'''{# ============================================================
   MENU SỔ XUỐNG V1
   - Chỉ điều hướng giao diện.
   - Không thay đổi route, dữ liệu hoặc nghiệp vụ.
   - Dùng auth_user đã có sẵn từ AccessControlMiddleware.
   ============================================================ #}
{% set menu_user = nguoi_dung if nguoi_dung is defined and nguoi_dung else (request.scope.get('auth_user') if request is defined else none) %}
{% if menu_user %}
    {% set menu_role = (menu_user.role_code or '')|upper %}
    {% set menu_path = request.url.path if request is defined else '/' %}

    <nav class="pc-global-nav" aria-label="Điều hướng chính">
        <div class="pc-global-nav__top">
            <a class="pc-global-nav__brand" href="/" title="Về trang chủ">
                <span class="pc-global-nav__brand-mark">PC</span>
                <span class="pc-global-nav__brand-text">
                    <strong>PHỔ CẬP GIÁO DỤC MẦM NON</strong>
                    <small>Hệ thống quản lý dữ liệu</small>
                </span>
            </a>

            <div class="pc-global-nav__account">
                <span class="pc-global-nav__account-name">{{ menu_user.full_name }}</span>
                <span class="pc-global-nav__account-unit">{{ menu_user.role_name }} · {{ menu_user.unit_name }}</span>
                <form method="post" action="/dang-xuat" class="pc-global-nav__logout-form">
                    <button type="submit" class="pc-global-nav__logout">Đăng xuất</button>
                </form>
            </div>
        </div>

        <div class="pc-global-nav__bar" data-pc-dropdown-menu>
            <a class="pc-global-nav__home {% if menu_path == '/' %}is-active{% endif %}" href="/">
                Trang chủ
            </a>

            {% if menu_role in ['ADMIN', 'SO'] %}
                <div class="pc-menu-group {% if menu_path.startswith('/tai-khoan') or menu_path.startswith('/xa') or menu_path.startswith('/truong') %}is-active{% endif %}">
                    <button type="button" class="pc-menu-trigger" aria-expanded="false">
                        1. Danh mục <span class="pc-menu-caret">▾</span>
                    </button>
                    <div class="pc-dropdown" role="menu">
                        <a href="/tai-khoan" role="menuitem">1.1. Quản lý tài khoản</a>
                        <a href="/xa" role="menuitem">1.2. Danh mục xã/phường</a>
                        <a href="/truong" role="menuitem">1.3. Danh mục trường</a>
                    </div>
                </div>
            {% elif menu_role == 'XA' %}
                <div class="pc-menu-group {% if menu_path.startswith('/truong') %}is-active{% endif %}">
                    <button type="button" class="pc-menu-trigger" aria-expanded="false">
                        1. Danh mục <span class="pc-menu-caret">▾</span>
                    </button>
                    <div class="pc-dropdown" role="menu">
                        <a href="/truong" role="menuitem">1.1. Trường thuộc xã/phường</a>
                    </div>
                </div>
            {% elif menu_role == 'TRUONG' %}
                <div class="pc-menu-group {% if menu_path.startswith('/tai-khoan') %}is-active{% endif %}">
                    <button type="button" class="pc-menu-trigger" aria-expanded="false">
                        1. Danh mục <span class="pc-menu-caret">▾</span>
                    </button>
                    <div class="pc-dropdown" role="menu">
                        <a href="/tai-khoan" role="menuitem">1.1. Tài khoản giáo viên</a>
                    </div>
                </div>
            {% endif %}

            <div class="pc-menu-group {% if menu_path.startswith('/dieu-tra') %}is-active{% endif %}">
                <button type="button" class="pc-menu-trigger" aria-expanded="false">
                    2. Điều tra hộ dân <span class="pc-menu-caret">▾</span>
                </button>
                <div class="pc-dropdown" role="menu">
                    <a href="/dieu-tra" role="menuitem">2.1. Danh sách đợt điều tra</a>

                    {% if menu_role in ['ADMIN', 'SO'] %}
                        <a href="/dieu-tra/khoi-tao-nam-hoc-toan-tinh" role="menuitem">2.2. Khởi tạo năm học toàn tỉnh</a>
                        <a href="/dieu-tra/dieu-hanh-trien-khai" role="menuitem">2.3. Điều hành triển khai</a>
                        <a href="/dieu-tra/trung-tam-phieu" role="menuitem">2.4. Trung tâm phiếu điều tra</a>
                        <a href="/dieu-tra/du-lieu-lich-su" role="menuitem">2.5. Dữ liệu lịch sử</a>
                        <a href="/dieu-tra/tong-hop-doi-chieu-hoc-sinh" role="menuitem">2.6. Tổng hợp đối chiếu học sinh</a>
                        <a href="/dieu-tra/don-doc-doi-chieu-hoc-sinh" role="menuitem">2.7. Theo dõi/đôn đốc đối chiếu</a>
                    {% elif menu_role == 'PHONG_BAN' %}
                        <a href="/dieu-tra/tong-hop-doi-chieu-hoc-sinh" role="menuitem">2.2. Tổng hợp đối chiếu học sinh</a>
                        <a href="/dieu-tra/don-doc-doi-chieu-hoc-sinh" role="menuitem">2.3. Theo dõi/đôn đốc đối chiếu</a>
                    {% elif menu_role == 'XA' %}
                        <span class="pc-dropdown__note">Phân công trường, khóa/mở và theo dõi tiến độ thực hiện trong từng đợt.</span>
                    {% elif menu_role == 'TRUONG' %}
                        <span class="pc-dropdown__note">Phân công giáo viên và xử lý phiếu thực hiện trong từng đợt.</span>
                    {% else %}
                        <span class="pc-dropdown__note">Mở đợt được giao để nhập và cập nhật các phiếu của bạn.</span>
                    {% endif %}
                </div>
            </div>

            {% if menu_role in ['ADMIN', 'SO'] %}
                <div class="pc-menu-group {% if menu_path.startswith('/hoc-sinh') %}is-active{% endif %}">
                    <button type="button" class="pc-menu-trigger" aria-expanded="false">
                        3. Học sinh <span class="pc-menu-caret">▾</span>
                    </button>
                    <div class="pc-dropdown" role="menu">
                        <a href="/hoc-sinh" role="menuitem">3.1. Danh sách học sinh</a>
                    </div>
                </div>
            {% endif %}

            <div class="pc-menu-group {% if menu_path.startswith('/doi-ngu') %}is-active{% endif %}">
                <button type="button" class="pc-menu-trigger" aria-expanded="false">
                    4. Đội ngũ <span class="pc-menu-caret">▾</span>
                </button>
                <div class="pc-dropdown" role="menu">
                    <a href="/doi-ngu" role="menuitem">4.1. Danh sách đội ngũ</a>
                    {% if menu_role in ['ADMIN', 'SO', 'TRUONG'] %}
                        <a href="/doi-ngu/cau-hinh-lop" role="menuitem">4.2. Cấu hình lớp</a>
                    {% endif %}
                </div>
            </div>

            <div class="pc-menu-group {% if menu_path.startswith('/bao-cao') %}is-active{% endif %}">
                <button type="button" class="pc-menu-trigger" aria-expanded="false">
                    5. Báo cáo <span class="pc-menu-caret">▾</span>
                </button>
                <div class="pc-dropdown pc-dropdown--right" role="menu">
                    <a href="/bao-cao" role="menuitem">5.1. Trung tâm báo cáo</a>
                    <a href="/bao-cao/bien-dong-theo-doi" role="menuitem">5.2. Theo dõi biến động</a>
                </div>
            </div>
        </div>
    </nav>

    <script>
        (function () {
            const nav = document.querySelector('[data-pc-dropdown-menu]');
            if (!nav || nav.dataset.pcReady === '1') return;
            nav.dataset.pcReady = '1';

            const groups = Array.from(nav.querySelectorAll('.pc-menu-group'));

            function closeGroup(group) {
                group.classList.remove('is-open');
                const trigger = group.querySelector('.pc-menu-trigger');
                if (trigger) trigger.setAttribute('aria-expanded', 'false');
            }

            function closeAll(except) {
                groups.forEach(function (group) {
                    if (group !== except) closeGroup(group);
                });
            }

            groups.forEach(function (group) {
                const trigger = group.querySelector('.pc-menu-trigger');
                if (!trigger) return;

                trigger.addEventListener('click', function (event) {
                    event.preventDefault();
                    const opening = !group.classList.contains('is-open');
                    closeAll(group);
                    group.classList.toggle('is-open', opening);
                    trigger.setAttribute('aria-expanded', opening ? 'true' : 'false');
                });

                group.addEventListener('mouseenter', function () {
                    if (window.matchMedia('(hover: hover)').matches) {
                        closeAll(group);
                        group.classList.add('is-open');
                        trigger.setAttribute('aria-expanded', 'true');
                    }
                });

                group.addEventListener('mouseleave', function () {
                    if (window.matchMedia('(hover: hover)').matches) {
                        closeGroup(group);
                    }
                });
            });

            document.addEventListener('click', function (event) {
                if (!nav.contains(event.target)) closeAll();
            });

            document.addEventListener('keydown', function (event) {
                if (event.key === 'Escape') closeAll();
            });
        }());
    </script>
{% endif %}
'''

CSS_BLOCK = r'''
/* === MENU SO XUONG V1: BAT DAU === */
.pc-global-nav {
    position: sticky;
    top: 0;
    z-index: 5000;
    width: 100%;
    font-family: Arial, Helvetica, sans-serif;
    color: #ffffff;
    box-shadow: 0 3px 12px rgba(18, 52, 86, 0.18);
}

.pc-global-nav__top {
    min-height: 58px;
    padding: 8px max(18px, calc((100% - 1280px) / 2));
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
    gap: 11px;
    color: #ffffff;
    text-decoration: none;
}

.pc-global-nav__brand-mark {
    width: 38px;
    height: 38px;
    flex: 0 0 38px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border-radius: 9px;
    background: #ffffff;
    color: #0d47a1;
    font-weight: 800;
    letter-spacing: -0.5px;
}

.pc-global-nav__brand-text {
    min-width: 0;
    display: flex;
    flex-direction: column;
    line-height: 1.16;
}

.pc-global-nav__brand-text strong {
    font-size: 15px;
    letter-spacing: 0.25px;
    white-space: nowrap;
}

.pc-global-nav__brand-text small {
    margin-top: 3px;
    font-size: 11px;
    opacity: 0.9;
}

.pc-global-nav__account {
    display: grid;
    grid-template-columns: minmax(0, auto) auto;
    grid-template-areas:
        "name logout"
        "unit logout";
    align-items: center;
    column-gap: 12px;
    text-align: right;
}

.pc-global-nav__account-name {
    grid-area: name;
    font-size: 14px;
    font-weight: 700;
}

.pc-global-nav__account-unit {
    grid-area: unit;
    max-width: 420px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: 11px;
    opacity: 0.9;
}

.pc-global-nav__logout-form {
    grid-area: logout;
    margin: 0;
}

.pc-global-nav__logout {
    min-height: 34px;
    padding: 7px 12px;
    border: 1px solid rgba(255,255,255,0.62);
    border-radius: 7px;
    background: rgba(255,255,255,0.12);
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
    min-height: 44px;
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
    min-height: 44px;
    padding: 0 15px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    border: 0;
    border-right: 1px solid #e5ebf1;
    background: transparent;
    color: #25364a;
    font: inherit;
    font-size: 14px;
    font-weight: 600;
    line-height: 1.2;
    text-decoration: none;
    white-space: nowrap;
    cursor: pointer;
}

.pc-global-nav__home:hover,
.pc-global-nav__home:focus-visible,
.pc-menu-trigger:hover,
.pc-menu-trigger:focus-visible,
.pc-menu-group.is-open > .pc-menu-trigger,
.pc-menu-group.is-active > .pc-menu-trigger,
.pc-global-nav__home.is-active {
    background: #eaf3ff;
    color: #0d5fb8;
    outline: none;
}

.pc-menu-group {
    position: relative;
    display: flex;
    align-items: stretch;
}

.pc-menu-caret {
    font-size: 11px;
    transition: transform 0.16s ease;
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
    max-width: min(390px, calc(100vw - 28px));
    padding: 7px 0;
    display: none;
    background: #ffffff;
    border: 1px solid #d9e2ec;
    border-radius: 0 0 8px 8px;
    box-shadow: 0 12px 28px rgba(30, 53, 79, 0.18);
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
    color: #26384d;
    font-size: 13px;
    font-weight: 500;
    line-height: 1.35;
    text-decoration: none;
    white-space: normal;
}

.pc-dropdown a:hover,
.pc-dropdown a:focus-visible {
    background: #edf5ff;
    color: #0d5fb8;
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
    .pc-global-nav__top {
        align-items: flex-start;
    }

    .pc-global-nav__account-unit {
        max-width: 260px;
    }

    .pc-global-nav__bar {
        overflow-x: auto;
        overflow-y: visible;
        scrollbar-width: thin;
    }

    .pc-global-nav__home,
    .pc-menu-trigger {
        padding-inline: 12px;
    }
}

@media (max-width: 680px) {
    .pc-global-nav {
        position: relative;
    }

    .pc-global-nav__top {
        flex-direction: column;
        align-items: stretch;
        gap: 8px;
    }

    .pc-global-nav__brand-text strong {
        white-space: normal;
    }

    .pc-global-nav__account {
        grid-template-columns: 1fr auto;
        text-align: left;
    }

    .pc-global-nav__account-unit {
        max-width: 100%;
    }

    .pc-global-nav__bar {
        flex-wrap: wrap;
        overflow: visible;
        padding: 4px 8px;
    }

    .pc-global-nav__home,
    .pc-menu-trigger {
        min-height: 40px;
        border-right: 0;
        border-radius: 6px;
    }

    .pc-dropdown,
    .pc-dropdown--right {
        position: fixed;
        top: auto;
        right: 10px;
        left: 10px;
        width: auto;
        max-width: none;
        border-radius: 8px;
    }
}

@media print {
    .pc-global-nav {
        display: none !important;
    }
}
/* === MENU SO XUONG V1: KET THUC === */
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


def inject_include(text: str) -> tuple[str, bool]:
    if INCLUDE_MARKER in text:
        return text, False
    match = re.search(r"<body\b[^>]*>", text, flags=re.IGNORECASE)
    if match is None:
        raise RuntimeError("Khong tim thay the <body> trong template")
    insert_at = match.end()
    addition = "\n" + INCLUDE_MARKER + "\n"
    return text[:insert_at] + addition + text[insert_at:], True


def update_css(text: str) -> str:
    pattern = re.compile(
        re.escape(CSS_START) + r".*?" + re.escape(CSS_END),
        flags=re.DOTALL,
    )
    cleaned = pattern.sub("", text).rstrip()
    return cleaned + "\n\n" + CSS_BLOCK.strip() + "\n"


def main() -> int:
    project = PROJECT
    if len(sys.argv) >= 2:
        project = Path(sys.argv[1]).expanduser().resolve()

    templates_dir = project / "app" / "templates"
    css_path = project / "app" / "static" / "css" / "style.css"
    db_path = project / "data" / "phocap.db"
    main_py = project / "app" / "main.py"

    print("\n" + "=" * 70)
    print("CAI DAT MENU SO XUONG V1")
    print("CHI DOI DIEU HUONG - KHONG DOI ROUTE - KHONG DOI DU LIEU")
    print("=" * 70)

    if not templates_dir.exists():
        raise FileNotFoundError(f"Khong tim thay: {templates_dir}")
    if not css_path.exists():
        raise FileNotFoundError(f"Khong tim thay: {css_path}")
    if not main_py.exists():
        raise FileNotFoundError(f"Khong tim thay: {main_py}")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = project / "exports" / f"backup_menu_so_xuong_v1_{stamp}"
    backup.mkdir(parents=True, exist_ok=False)

    db_hash_before = sha256(db_path)
    main_hash_before = sha256(main_py)

    html_files = sorted(templates_dir.rglob("*.html"))
    targets: list[Path] = []
    for file_path in html_files:
        rel = file_path.relative_to(templates_dir).as_posix()
        if rel in EXCLUDED_TEMPLATES:
            continue
        if rel.startswith("partials/"):
            continue
        targets.append(file_path)

    partial_path = templates_dir / "partials" / "dropdown_menu_v1.html"
    changed_files: list[str] = []
    created_files: list[str] = []
    backed_up: list[str] = []

    print("\nBUOC 1 - SAO LUU AN TOAN")
    files_to_backup = [css_path, main_py, *targets]
    if partial_path.exists():
        files_to_backup.append(partial_path)
    if db_path.exists():
        # Chỉ tạo ảnh chụp dữ liệu để dự phòng; script khôi phục menu KHÔNG tự phục hồi DB.
        files_to_backup.append(db_path)

    for source in files_to_backup:
        rel = source.relative_to(project)
        copy_with_parent(source, backup / rel)
        backed_up.append(rel.as_posix())

    print(f"Ban sao an toan: {backup}")

    try:
        print("\nBUOC 2 - TAO MENU DUNG CHUNG THEO VAI TRO")
        partial_path.parent.mkdir(parents=True, exist_ok=True)
        if not partial_path.exists():
            created_files.append(partial_path.relative_to(project).as_posix())
        partial_path.write_text(MENU_TEMPLATE, encoding="utf-8")
        changed_files.append(partial_path.relative_to(project).as_posix())
        print("Da tao/cap nhat: app/templates/partials/dropdown_menu_v1.html")

        print("\nBUOC 3 - BO SUNG CSS RIENG CHO MENU")
        css_text = css_path.read_text(encoding="utf-8-sig")
        css_path.write_text(update_css(css_text), encoding="utf-8")
        changed_files.append(css_path.relative_to(project).as_posix())
        print("Da cap nhat: app/static/css/style.css")

        print("\nBUOC 4 - GAN MENU VAO CAC GIAO DIEN DANG NHAP")
        injected = 0
        already = 0
        for template_path in targets:
            rel = template_path.relative_to(project).as_posix()
            text = template_path.read_text(encoding="utf-8-sig")
            new_text, did_change = inject_include(text)
            if did_change:
                template_path.write_text(new_text, encoding="utf-8")
                changed_files.append(rel)
                injected += 1
            else:
                already += 1
        print(f"Da gan menu moi vao {injected} template; {already} template da co san marker.")
        print("Khong gan vao trang dang nhap va trang in phieu thuc dia.")

        print("\nBUOC 5 - KIEM TRA AN TOAN")
        # Jinja2 là phụ thuộc sẵn có của FastAPI/Jinja trong dự án.
        from jinja2 import Environment, FileSystemLoader

        env = Environment(loader=FileSystemLoader(str(templates_dir)))
        env.get_template("partials/dropdown_menu_v1.html")
        syntax_errors: list[str] = []
        missing_include: list[str] = []
        for template_path in targets:
            rel_t = template_path.relative_to(templates_dir).as_posix()
            try:
                env.parse(template_path.read_text(encoding="utf-8-sig"))
            except Exception as exc:
                syntax_errors.append(f"{rel_t}: {exc}")
            if INCLUDE_MARKER not in template_path.read_text(encoding="utf-8-sig"):
                missing_include.append(rel_t)

        if syntax_errors:
            raise RuntimeError("Loi cu phap Jinja:\n" + "\n".join(syntax_errors[:10]))
        if missing_include:
            raise RuntimeError("Template chua co menu:\n" + "\n".join(missing_include[:10]))

        if sha256(main_py) != main_hash_before:
            raise RuntimeError("app/main.py da bi thay doi ngoai du kien.")
        if sha256(db_path) != db_hash_before:
            raise RuntimeError("Co so du lieu phocap.db da bi thay doi ngoai du kien.")

        manifest = {
            "version": VERSION,
            "installed_at": datetime.now().isoformat(timespec="seconds"),
            "project": str(project),
            "backup": str(backup),
            "changed_files": sorted(set(changed_files)),
            "created_files": sorted(set(created_files)),
            "backed_up": sorted(set(backed_up)),
            "excluded_templates": sorted(EXCLUDED_TEMPLATES),
            "database_sha256_before": db_hash_before,
            "database_sha256_after": sha256(db_path),
            "main_py_sha256_before": main_hash_before,
            "main_py_sha256_after": sha256(main_py),
        }
        (backup / "MENU_V1_MANIFEST.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        latest = project / "exports" / "menu_so_xuong_v1_backup_moi_nhat.txt"
        latest.write_text(str(backup), encoding="utf-8")

        print("Jinja: DAT")
        print("app/main.py: KHONG DOI")
        print("data/phocap.db: KHONG DOI")
        print(f"So template giao dien co menu: {len(targets)}")
        print("\n" + "=" * 70)
        print("CAI DAT MENU SO XUONG V1 THANH CONG")
        print("=" * 70)
        print(f"Ban sao an toan: {backup}")
        print("Khoi dong lai Uvicorn va nhan Ctrl+F5 tren trinh duyet de xem menu moi.")
        return 0

    except Exception:
        print("\nCAI DAT KHONG THANH CONG - DANG TU DONG KHOI PHUC GIAO DIEN CU...")
        traceback.print_exc()

        # Chỉ khôi phục file giao diện/CSS; không tự ghi đè DB.
        for source in [css_path, main_py, *targets]:
            rel = source.relative_to(project)
            saved = backup / rel
            if saved.exists():
                copy_with_parent(saved, source)
        saved_partial = backup / partial_path.relative_to(project)
        if saved_partial.exists():
            copy_with_parent(saved_partial, partial_path)
        elif partial_path.exists():
            partial_path.unlink()

        print("DA KHOI PHUC CAC TEP GIAO DIEN CU.")
        print("CO SO DU LIEU KHONG BI GHI DE.")
        print(f"Ban sao an toan: {backup}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
