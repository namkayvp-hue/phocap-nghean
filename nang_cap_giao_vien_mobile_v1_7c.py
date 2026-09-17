from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import traceback
from datetime import datetime
from pathlib import Path

PROJECT = Path(r"C:\PhoCap").resolve()
PYTHON = PROJECT / ".venv" / "Scripts" / "python.exe"

MAIN = PROJECT / "app" / "main.py"
DB = PROJECT / "data" / "phocap.db"
MENU = PROJECT / "app" / "templates" / "partials" / "dropdown_menu_v1.html"
INDEX = PROJECT / "app" / "templates" / "surveys" / "index.html"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = PROJECT / "exports" / f"backup_giao_vien_mobile_v1_7c_{STAMP}"
MANIFEST = BACKUP / "manifest.json"

OLD_MENU_START = "{# === GIAO_VIEN_MOBILE_V1_7A_START === #}"
OLD_MENU_END = "{# === GIAO_VIEN_MOBILE_V1_7A_END === #}"

OLD_INDEX_START = "{# === GV_MOBILE_V17B_INDEX_START === #}"
OLD_INDEX_END = "{# === GV_MOBILE_V17B_INDEX_END === #}"

NEW_START = "{# === GV_MOBILE_V17C_HOME_START === #}"
NEW_END = "{# === GV_MOBILE_V17C_HOME_END === #}"

NEW_BLOCK = """
{# === GV_MOBILE_V17C_HOME_START === #}
{% if nguoi_dung.role_code == 'GIAO_VIEN' %}
<style>
.pc-gv-v17c-home {
    display: none;
}

@media (max-width: 760px) {
    /* Màn hình chính giáo viên trên điện thoại:
       chỉ Năm học + Phiếu phân công. */
    .page-main > :not(.pc-gv-v17c-home) {
        display: none !important;
    }

    .pc-gv-v17c-home {
        display: block;
        padding: 14px 12px 24px;
    }

    .pc-gv-v17c-card {
        padding: 16px;
        background: #ffffff;
        border: 1px solid #d7e2ed;
        border-radius: 14px;
        box-shadow: 0 3px 12px rgba(30, 78, 125, .08);
    }

    .pc-gv-v17c-title {
        margin: 0 0 12px;
        color: #123f73;
        font-size: 21px;
        font-weight: 850;
    }

    .pc-gv-v17c-label {
        display: block;
        margin-bottom: 7px;
        color: #17263a;
        font-size: 14px;
        font-weight: 800;
    }

    .pc-gv-v17c-select {
        width: 100%;
        min-height: 50px;
        padding: 8px 12px;
        border: 1px solid #bccdde;
        border-radius: 11px;
        background: #fff;
        color: #17263a;
        font-size: 16px;
    }

    .pc-gv-v17c-section {
        margin-top: 16px;
    }

    .pc-gv-v17c-section-title {
        margin: 0 0 9px;
        color: #123f73;
        font-size: 17px;
        font-weight: 850;
    }

    .pc-gv-v17c-list {
        display: grid;
        gap: 9px;
    }

    .pc-gv-v17c-batch {
        display: block;
        padding: 13px;
        border: 1px solid #d6e1ec;
        border-radius: 11px;
        background: #f8fbff;
        text-decoration: none !important;
        color: #123f73 !important;
    }

    .pc-gv-v17c-batch strong {
        display: block;
        font-size: 15px;
        line-height: 1.3;
    }

    .pc-gv-v17c-batch span {
        display: block;
        margin-top: 4px;
        color: #60758a;
        font-size: 12px;
        font-weight: 600;
    }

    .pc-gv-v17c-empty {
        padding: 14px;
        border: 1px dashed #bfd0df;
        border-radius: 11px;
        color: #60758a;
        background: #fbfdff;
        font-size: 13px;
        text-align: center;
    }
}
</style>

<section class="pc-gv-v17c-home">
    <div class="pc-gv-v17c-card">
        <h2 class="pc-gv-v17c-title">Điều tra thực địa</h2>

        <form method="get" action="/dieu-tra" id="pc-gv-v17c-year-form">
            <label class="pc-gv-v17c-label" for="pc-gv-v17c-year">
                Năm học
            </label>

            <select
                class="pc-gv-v17c-select"
                id="pc-gv-v17c-year"
                name="school_year_id"
            >
                <option value="">-- Chọn năm học --</option>
                {% for nam_hoc in school_years %}
                    <option
                        value="{{ nam_hoc.id }}"
                        {% if nam_hoc.id == selected_school_year_id %}selected{% endif %}
                    >
                        {{ nam_hoc.code }}
                    </option>
                {% endfor %}
            </select>
        </form>

        <div class="pc-gv-v17c-section">
            <div class="pc-gv-v17c-section-title">📋 Phiếu phân công</div>

            {% if selected_school_year_id %}
                <div class="pc-gv-v17c-list">
                    {% for dot in survey_batches %}
                        <a
                            class="pc-gv-v17c-batch"
                            href="/dieu-tra/{{ dot.id }}/ho-dan"
                        >
                            <strong>{{ dot.name }}</strong>
                            <span>
                                {{ batch_visible_counts.get(dot.id, 0) }}
                                phiếu được phân công
                            </span>
                        </a>
                    {% else %}
                        <div class="pc-gv-v17c-empty">
                            Năm học này chưa có phiếu nào được phân công cho bạn.
                        </div>
                    {% endfor %}
                </div>
            {% else %}
                <div class="pc-gv-v17c-empty">
                    Chọn năm học để xem phiếu phân công.
                </div>
            {% endif %}
        </div>
    </div>
</section>

<script>
window.addEventListener('load', function () {
    if (window.innerWidth > 760) return;

    const year = document.getElementById('pc-gv-v17c-year');
    const form = document.getElementById('pc-gv-v17c-year-form');

    if (year && form) {
        year.addEventListener('change', function () {
            form.submit();
        });
    }
});
</script>
{% endif %}
{# === GV_MOBILE_V17C_HOME_END === #}
"""


def sha256(path: Path):
    if not path.exists():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def backup(path: Path, manifest: dict):
    rel = path.relative_to(PROJECT).as_posix()
    manifest[rel] = {"existed": path.exists()}
    if path.exists():
        dest = BACKUP / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)


def restore(manifest: dict):
    for rel, info in manifest.items():
        if not info.get("existed"):
            continue
        src = BACKUP / rel
        dst = PROJECT / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def strip_block(text: str, start: str, end: str) -> str:
    while start in text and end in text:
        a = text.index(start)
        b = text.index(end, a) + len(end)
        text = text[:a] + text[b:]
    return text


def patch_menu(text: str) -> str:
    # Bỏ thanh 3 nút cũ: Phiếu phân công - Hộ dân - Nhập nhanh.
    text = strip_block(text, OLD_MENU_START, OLD_MENU_END)

    # Sau V1.7C không được còn hai nút Hộ dân / Nhập nhanh ở header mobile.
    if OLD_MENU_START in text or OLD_MENU_END in text:
        raise RuntimeError("Khong the go bo block mobile V1.7A cu.")
    return text


def patch_index(text: str) -> str:
    # Bỏ block mobile V1.7B trên màn hình chính để tránh lặp.
    text = strip_block(text, OLD_INDEX_START, OLD_INDEX_END)
    text = strip_block(text, NEW_START, NEW_END)

    anchor = '<main class="page-main">'
    if anchor not in text:
        raise RuntimeError("Khong tim thay <main class='page-main'> trong surveys/index.html.")

    return text.replace(anchor, anchor + "\n" + NEW_BLOCK, 1)


def main():
    print("=" * 80)
    print("GIAO VIEN MOBILE V1.7C - MAN HINH CHINH TOI GIAN")
    print("CHI CON: NAM HOC + PHIEU PHAN CONG")
    print("=" * 80)

    for path in [PYTHON, MAIN, DB, MENU, INDEX]:
        if not path.exists():
            raise RuntimeError(f"Khong tim thay: {path}")

    before_main = sha256(MAIN)
    before_db = sha256(DB)

    manifest = {}
    BACKUP.mkdir(parents=True, exist_ok=False)

    for path in [MENU, INDEX]:
        backup(path, manifest)

    MANIFEST.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    try:
        MENU.write_text(
            patch_menu(MENU.read_text(encoding="utf-8-sig")),
            encoding="utf-8",
        )

        INDEX.write_text(
            patch_index(INDEX.read_text(encoding="utf-8-sig")),
            encoding="utf-8",
        )

        for cache in (PROJECT / "app").rglob("__pycache__"):
            if cache.is_dir():
                shutil.rmtree(cache, ignore_errors=True)

        checker = PROJECT / "check_giao_vien_mobile_v1_7c.py"
        checker.write_text(
            "from pathlib import Path\n"
            "from jinja2 import Environment, FileSystemLoader\n"
            "root=Path(r'C:\\\\PhoCap\\\\app\\\\templates')\n"
            "env=Environment(loader=FileSystemLoader(str(root)))\n"
            "env.get_template('partials/dropdown_menu_v1.html')\n"
            "env.get_template('surveys/index.html')\n"
            "text=(root/'surveys'/'index.html').read_text(encoding='utf-8')\n"
            "assert 'pc-gv-v17c-year' in text\n"
            "assert 'Phiếu phân công' in text\n"
            "print('Jinja: DAT')\n"
            "print('Man hinh chinh GV mobile V1.7C: DAT')\n",
            encoding="utf-8",
        )

        subprocess.run(
            [str(PYTHON), str(checker)],
            cwd=PROJECT,
            check=True,
        )

        if sha256(MAIN) != before_main:
            raise RuntimeError("app/main.py da thay doi.")
        if sha256(DB) != before_db:
            raise RuntimeError("data/phocap.db da thay doi.")

        menu_text = MENU.read_text(encoding="utf-8")
        index_text = INDEX.read_text(encoding="utf-8")

        if "pc-teacher-mobile-actions" in menu_text:
            raise RuntimeError("Thanh 3 nut mobile cu van con.")
        if "pc-gv-v17c-year" not in index_text:
            raise RuntimeError("Thieu chon nam hoc V1.7C.")

        print("")
        print("DIEN THOAI GIAO VIEN:")
        print(" - Nam hoc: DAT")
        print(" - Phieu phan cong: DAT")
        print(" - Nut Ho dan tren man hinh chinh: DA BO")
        print(" - Nut Nhap nhanh tren man hinh chinh: DA BO")
        print("")
        print("Ben trong Phieu phan cong:")
        print(" - So phieu - Ho dan - Nhap nhanh: GIU NGUYEN")
        print(" - Nhap nhanh tung ho: GIU NGUYEN")
        print("")
        print("Desktop giao vien: GIU NGUYEN")
        print("app/main.py: KHONG DOI")
        print("data/phocap.db: KHONG DOI")
        print("Route: KHONG DOI")
        print("Luong nghiep vu: KHONG DOI")
        print("")
        print("CAI DAT GIAO VIEN MOBILE V1.7C THANH CONG")
        print("Backup:", BACKUP)
        return 0

    except Exception:
        traceback.print_exc()
        restore(manifest)
        print("DA KHOI PHUC TU DONG.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
