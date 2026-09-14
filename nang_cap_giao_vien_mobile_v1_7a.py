from __future__ import annotations

import hashlib
import shutil
import subprocess
import traceback
from datetime import datetime
from pathlib import Path

PROJECT = Path(r"C:\PhoCap").resolve()
PYTHON = PROJECT / ".venv" / "Scripts" / "python.exe"

MENU = PROJECT / "app" / "templates" / "partials" / "dropdown_menu_v1.html"
MAIN = PROJECT / "app" / "main.py"
DB = PROJECT / "data" / "phocap.db"
ROUTERS = PROJECT / "app" / "routers"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = PROJECT / "exports" / f"backup_giao_vien_mobile_v1_7a_{STAMP}"

START = "{# === GIAO_VIEN_MOBILE_V1_7A_START === #}"
END = "{# === GIAO_VIEN_MOBILE_V1_7A_END === #}"

MOBILE_BLOCK = """
{# === GIAO_VIEN_MOBILE_V1_7A_START === #}
{% if menu_role == 'GIAO_VIEN' %}
<style id="pc-teacher-mobile-v17a-style">
.pc-teacher-mobile-actions { display: none; }

@media (max-width: 760px) {
    .pc-global-nav__bar { display: none !important; }

    .pc-global-nav__top {
        min-height: 52px;
        padding: 6px 10px;
        gap: 8px;
    }

    .pc-global-nav__brand-text strong {
        font-size: 12px;
        white-space: normal;
    }

    .pc-global-nav__brand-text small { display: none; }

    .pc-global-nav__brand-mark {
        width: 32px;
        height: 32px;
        flex-basis: 32px;
    }

    .pc-global-nav__account-unit { display: none; }

    .pc-global-nav__account-name {
        max-width: 112px;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        font-size: 12px;
    }

    .pc-global-nav__logout {
        min-height: 32px;
        padding: 6px 9px;
        font-size: 11px;
    }

    .pc-teacher-mobile-actions {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 8px;
        width: 100%;
        padding: 9px 10px 10px;
        background: #ffffff;
        border-bottom: 1px solid #d8e1eb;
    }

    .pc-teacher-mobile-action {
        min-height: 64px;
        padding: 8px 5px;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        gap: 4px;
        border: 1px solid #cbd9e8;
        border-radius: 12px;
        background: #f7fbff;
        color: #174a7e !important;
        text-align: center;
        text-decoration: none !important;
        font-size: 12px;
        font-weight: 700;
        line-height: 1.15;
        box-shadow: 0 2px 7px rgba(20, 71, 120, .08);
    }

    .pc-teacher-mobile-action:active,
    .pc-teacher-mobile-action:focus-visible {
        background: #e8f3ff;
        border-color: #78aee2;
        outline: none;
    }

    .pc-teacher-mobile-action__icon {
        font-size: 22px;
        line-height: 1;
    }

    .pc-teacher-mobile-action__sub {
        display: block;
        font-size: 9px;
        font-weight: 500;
        color: #627a91;
    }

    body { -webkit-text-size-adjust: 100%; }
}
</style>

<div class="pc-teacher-mobile-actions" aria-label="Điều tra thực địa">
    <a
        class="pc-teacher-mobile-action"
        href="/dieu-tra"
        title="Xem các đợt và phiếu được phân công trực tiếp"
    >
        <span class="pc-teacher-mobile-action__icon">📋</span>
        <span>Phiếu phân công</span>
    </a>

    <a
        class="pc-teacher-mobile-action"
        href="/dieu-tra"
        data-batch-template="/dieu-tra/{batch_id}/ho-dan"
        title="Danh sách hộ thuộc đợt đang làm việc"
    >
        <span class="pc-teacher-mobile-action__icon">🏠</span>
        <span>Hộ dân</span>
    </a>

    <a
        class="pc-teacher-mobile-action"
        href="/dieu-tra"
        data-batch-template="/dieu-tra/{batch_id}/ho-dan"
        data-pc-mobile-quick
        title="Chọn hộ để nhập nhanh; nếu đang ở một hộ sẽ vào thẳng màn hình nhập nhanh"
    >
        <span class="pc-teacher-mobile-action__icon">✍️</span>
        <span>Nhập nhanh</span>
        <span class="pc-teacher-mobile-action__sub">thực địa</span>
    </a>
</div>

<script id="pc-teacher-mobile-v17a-script">
window.addEventListener('load', function () {
    const quick = document.querySelector('[data-pc-mobile-quick]');
    if (!quick) return;

    const match = window.location.pathname.match(
        /^\\/dieu-tra\\/(\\d+)\\/ho-dan\\/(\\d+)(?:\\/|$)/
    );

    if (match) {
        quick.setAttribute(
            'href',
            '/dieu-tra/' + match[1] + '/ho-dan/' + match[2] + '/nhap-nhanh'
        );
        quick.removeAttribute('data-batch-template');
        quick.setAttribute('title', 'Nhập nhanh hộ đang mở');
    }
});
</script>
{% endif %}
{# === GIAO_VIEN_MOBILE_V1_7A_END === #}
"""


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
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        h.update(path.relative_to(root).as_posix().encode("utf-8"))
        h.update(path.read_bytes())
    return h.hexdigest()


def remove_existing_block(text: str) -> str:
    while START in text and END in text:
        start = text.index(START)
        end = text.index(END, start) + len(END)
        text = text[:start] + text[end:]
    return text


def patch_menu():
    text = MENU.read_text(encoding="utf-8-sig")
    text = remove_existing_block(text)

    anchor = '<div class="pc-global-nav__bar" data-pc-dropdown-menu-v15>'
    if anchor not in text:
        raise RuntimeError(
            "Khong tim thay thanh menu V1.5/V1.6 hien tai. "
            "Khong sua de tranh lam hong giao dien."
        )

    text = text.replace(anchor, MOBILE_BLOCK + "\n" + anchor, 1)

    for required in [
        "Phiếu phân công",
        "Hộ dân",
        "Nhập nhanh",
        "menu_role == 'GIAO_VIEN'",
        'data-batch-template="/dieu-tra/{batch_id}/ho-dan"',
    ]:
        if required not in text:
            raise RuntimeError("Thieu thanh phan mobile: " + required)

    MENU.write_text(text, encoding="utf-8")


def main():
    print("")
    print("=" * 76)
    print("GIAO DIEN GIAO VIEN DIEN THOAI V1.7A")
    print("3 NUT: PHIEU PHAN CONG - HO DAN - NHAP NHANH")
    print("=" * 76)
    print("Desktop: GIU NGUYEN")
    print("Route: KHONG DOI")
    print("Du lieu: KHONG DOI")
    print("Luong nghiep vu: KHONG DOI")

    for path in [PROJECT, PYTHON, MENU, MAIN, DB, ROUTERS]:
        if not path.exists():
            print("Khong tim thay:", path)
            return 1

    BACKUP.mkdir(parents=True, exist_ok=False)
    saved_menu = BACKUP / MENU.relative_to(PROJECT)
    saved_menu.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(MENU, saved_menu)

    main_before = sha256(MAIN)
    db_before = sha256(DB)
    routers_before = tree_hash(ROUTERS)

    print("Ban sao an toan:", BACKUP)

    try:
        patch_menu()

        for cache in (PROJECT / "app").rglob("__pycache__"):
            if cache.is_dir():
                shutil.rmtree(cache, ignore_errors=True)

        check_file = PROJECT / "check_giao_vien_mobile_v1_7a.py"
        check_file.write_text(
            "from pathlib import Path\n"
            "from jinja2 import Environment, FileSystemLoader\n"
            "root=Path(r'C:\\\\PhoCap\\\\app\\\\templates')\n"
            "env=Environment(loader=FileSystemLoader(str(root)))\n"
            "env.get_template('partials/dropdown_menu_v1.html')\n"
            "text=(root/'partials'/'dropdown_menu_v1.html').read_text(encoding='utf-8')\n"
            "for key in ['Phiếu phân công','Hộ dân','Nhập nhanh',\"menu_role == 'GIAO_VIEN'\"]:\n"
            "    assert key in text, key\n"
            "print('Jinja: DAT')\n"
            "print('Giao vien mobile 3 nut: DAT')\n",
            encoding="utf-8",
        )
        subprocess.run([str(PYTHON), str(check_file)], cwd=PROJECT, check=True)

        if sha256(MAIN) != main_before:
            raise RuntimeError("app/main.py bi thay doi.")
        if sha256(DB) != db_before:
            raise RuntimeError("data/phocap.db bi thay doi.")
        if tree_hash(ROUTERS) != routers_before:
            raise RuntimeError("app/routers bi thay doi.")

        print("")
        print("GIAO VIEN DIEN THOAI:")
        print(" - Phieu phan cong: DAT")
        print(" - Ho dan: DAT")
        print(" - Nhap nhanh: DAT")
        print("GIAO VIEN MAY TINH: GIU NGUYEN MENU DAY DU")
        print("CAC CAP SO/XA/TRUONG: KHONG DOI")
        print("app/main.py: KHONG DOI")
        print("app/routers: KHONG DOI")
        print("data/phocap.db: KHONG DOI")
        print("Route: KHONG DOI")
        print("Luong nghiep vu: KHONG DOI")
        print("")
        print("CAI DAT GIAO DIEN GIAO VIEN DIEN THOAI V1.7A THANH CONG")
        return 0

    except Exception as exc:
        print("")
        print("CAI DAT KHONG THANH CONG:")
        print(exc)
        traceback.print_exc()
        shutil.copy2(saved_menu, MENU)
        print("DA KHOI PHUC MENU CU.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
