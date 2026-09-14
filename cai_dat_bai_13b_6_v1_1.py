from __future__ import annotations

import json
import os
import shutil
import traceback
from datetime import datetime
from pathlib import Path

PROJECT = Path(os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")).resolve()

GV = PROJECT / "app" / "templates" / "report_inputs" / "gv_mn01.html"
CSVC = PROJECT / "app" / "templates" / "report_inputs" / "csvc_mn01.html"
STRUCT = PROJECT / "app" / "templates" / "report_inputs" / "structured_school_form.html"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = PROJECT / "exports" / f"backup_bai_13b_6_v1_1_{STAMP}"
MANIFEST = BACKUP / "manifest.json"

FILES = [
    "app/templates/report_inputs/gv_mn01.html",
    "app/templates/report_inputs/csvc_mn01.html",
    "app/templates/report_inputs/structured_school_form.html",
]

MARKER = "BAI_13B_6_V1_1_SAFE_SCOPE_SUBMIT"


def _read(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(f"Không tìm thấy tệp: {path}")
    return path.read_text(encoding="utf-8-sig")


def _backup() -> list[dict]:
    BACKUP.mkdir(parents=True, exist_ok=False)
    manifest = []
    for rel in FILES:
        src = PROJECT / rel
        existed = src.exists()
        manifest.append({"path": rel, "existed": existed})
        if existed:
            dst = BACKUP / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    MANIFEST.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return manifest


def _restore(manifest: list[dict]) -> None:
    for item in reversed(manifest):
        target = PROJECT / item["path"]
        if item["existed"]:
            src = BACKUP / item["path"]
            if src.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, target)


def _patch_gv(text: str) -> str:
    if MARKER in text:
        return text

    old_reload = """    function reloadSchools() {
        if (school) school.value = '';
        form.submit();
    }
"""
    new_reload = """    // === BAI_13B_6_V1_1_SAFE_SCOPE_SUBMIT ===
    function safeScopeSubmit() {
        const params = new URLSearchParams();

        if (year && year.value) {
            params.set('school_year_id', year.value);
        }

        if (commune && commune.value) {
            params.set('commune_id', commune.value);
        }

        if (school && school.value) {
            params.set('school_id', school.value);
        }

        const query = params.toString();
        window.location.href = form.action + (query ? '?' + query : '');
    }

    function reloadSchools() {
        if (school) school.value = '';
        safeScopeSubmit();
    }
"""
    if old_reload not in text:
        raise RuntimeError("Không tìm thấy đoạn reloadSchools trong MN-01-GV.")
    text = text.replace(old_reload, new_reload, 1)

    old_year = """    if (year) {
        year.addEventListener('change', function () {
            if (school) school.value = '';
            form.submit();
        });
    }
"""
    new_year = """    if (year) {
        year.addEventListener('change', function () {
            if (school) school.value = '';
            safeScopeSubmit();
        });
    }
"""
    if old_year not in text:
        raise RuntimeError("Không tìm thấy xử lý đổi năm trong MN-01-GV.")
    text = text.replace(old_year, new_year, 1)

    # Khi người dùng bấm Mở dữ liệu, bảo đảm không bao giờ gửi school_id="" hoặc commune_id="".
    inject_anchor = """    if (school) {
        school.addEventListener('change', syncOpenButton);
    }

    syncOpenButton();
"""
    inject_new = """    if (school) {
        school.addEventListener('change', syncOpenButton);
    }

    form.addEventListener('submit', function (event) {
        if ((school && !school.value) || (commune && !commune.value)) {
            event.preventDefault();
            safeScopeSubmit();
        }
    });

    syncOpenButton();
"""
    if inject_anchor not in text:
        raise RuntimeError("Không tìm thấy điểm chèn submit an toàn trong MN-01-GV.")
    return text.replace(inject_anchor, inject_new, 1)


def _patch_csvc(text: str) -> str:
    if MARKER in text:
        return text

    old_reload = """    function reloadSchools() {
        if (school) school.value = '';
        form.submit();
    }
"""
    new_reload = """    // === BAI_13B_6_V1_1_SAFE_SCOPE_SUBMIT ===
    function safeScopeSubmit() {
        const params = new URLSearchParams();

        if (year && year.value) {
            params.set('school_year_id', year.value);
        }

        if (commune && commune.value) {
            params.set('commune_id', commune.value);
        }

        if (school && school.value) {
            params.set('school_id', school.value);
        }

        const query = params.toString();
        window.location.href = form.action + (query ? '?' + query : '');
    }

    function reloadSchools() {
        if (school) school.value = '';
        safeScopeSubmit();
    }
"""
    if old_reload not in text:
        raise RuntimeError("Không tìm thấy đoạn reloadSchools trong MN-01-CSVC.")
    text = text.replace(old_reload, new_reload, 1)

    old_year = """    if (year) {
        year.addEventListener('change', function () {
            if (school) school.value = '';
            form.submit();
        });
    }
"""
    new_year = """    if (year) {
        year.addEventListener('change', function () {
            if (school) school.value = '';
            safeScopeSubmit();
        });
    }
"""
    if old_year not in text:
        raise RuntimeError("Không tìm thấy xử lý đổi năm trong MN-01-CSVC.")
    text = text.replace(old_year, new_year, 1)

    inject_anchor = """    if (school) {
        school.addEventListener('change', syncOpenButton);
    }

    syncOpenButton();
"""
    inject_new = """    if (school) {
        school.addEventListener('change', syncOpenButton);
    }

    form.addEventListener('submit', function (event) {
        if ((school && !school.value) || (commune && !commune.value)) {
            event.preventDefault();
            safeScopeSubmit();
        }
    });

    syncOpenButton();
"""
    if inject_anchor not in text:
        raise RuntimeError("Không tìm thấy điểm chèn submit an toàn trong MN-01-CSVC.")
    return text.replace(inject_anchor, inject_new, 1)


def _patch_structured(text: str) -> str:
    if MARKER in text:
        return text

    old_block = """        function syncOpen() {
            if (!open || !school) return;
            open.disabled = !school.value;
        }

        if (year) {
            year.addEventListener('change', function () {
                if (school) school.value = '';
                filterForm.submit();
            });
        }
        if (commune) {
            commune.addEventListener('change', function () {
                if (school) school.value = '';
                filterForm.submit();
            });
        }
        if (school) school.addEventListener('change', syncOpen);
        syncOpen();
"""
    new_block = """        function syncOpen() {
            if (!open || !school) return;
            open.disabled = !school.value;
        }

        // === BAI_13B_6_V1_1_SAFE_SCOPE_SUBMIT ===
        function safeScopeSubmit() {
            const params = new URLSearchParams();

            if (year && year.value) {
                params.set('school_year_id', year.value);
            }

            if (commune && commune.value) {
                params.set('commune_id', commune.value);
            }

            if (school && school.value) {
                params.set('school_id', school.value);
            }

            const query = params.toString();
            window.location.href = filterForm.action + (query ? '?' + query : '');
        }

        if (year) {
            year.addEventListener('change', function () {
                if (school) school.value = '';
                safeScopeSubmit();
            });
        }

        if (commune) {
            commune.addEventListener('change', function () {
                if (school) school.value = '';
                safeScopeSubmit();
            });
        }

        if (school) {
            school.addEventListener('change', syncOpen);
        }

        filterForm.addEventListener('submit', function (event) {
            if ((school && !school.value) || (commune && !commune.value)) {
                event.preventDefault();
                safeScopeSubmit();
            }
        });

        syncOpen();
"""
    if old_block not in text:
        raise RuntimeError("Không tìm thấy JS bộ lọc trong màn hình TH/THCS chuyên biệt.")
    return text.replace(old_block, new_block, 1)


def _verify_jinja() -> None:
    from jinja2 import Environment, FileSystemLoader

    env = Environment(
        loader=FileSystemLoader(str(PROJECT / "app" / "templates"))
    )
    for name in [
        "report_inputs/gv_mn01.html",
        "report_inputs/csvc_mn01.html",
        "report_inputs/structured_school_form.html",
    ]:
        env.get_template(name)


def main() -> int:
    print("=" * 88)
    print("BÀI 13B-6 V1.1 - SỬA LỖI CHỌN XÃ/PHƯỜNG -> TRƯỜNG")
    print("=" * 88)
    print("")
    print("Lỗi hiện tại:")
    print('  URL sinh ra school_id= rỗng -> FastAPI báo int_parsing.')
    print("")
    print("Bản sửa:")
    print("  - Không gửi school_id nếu chưa chọn trường.")
    print("  - Không gửi commune_id nếu đang để trống.")
    print("  - Áp dụng MN-01-GV, MN-01-CSVC và 4 màn hình TH/THCS mới.")
    print("  - Không đổi database, dữ liệu hay cấu trúc menu.")
    print("")

    gv_text = _read(GV)
    csvc_text = _read(CSVC)
    struct_text = _read(STRUCT)

    required = [
        ("MN-01-GV", gv_text, "BAI_13B_4_V1_CASCADE_GV_START"),
        ("MN-01-CSVC", csvc_text, "BAI_13B_4_V1_CASCADE_CSVC_START"),
        ("Bài 13B-6", struct_text, "BÀI 13B-6"),
    ]
    for label, text, marker in required:
        if marker not in text:
            raise RuntimeError(
                f"Không tìm thấy nền {label}: {marker}. "
                "Dừng cài để tránh sửa nhầm phiên bản."
            )

    manifest = _backup()

    try:
        GV.write_text(_patch_gv(gv_text), encoding="utf-8")
        CSVC.write_text(_patch_csvc(csvc_text), encoding="utf-8")
        STRUCT.write_text(_patch_structured(struct_text), encoding="utf-8")

        _verify_jinja()

        for path in (GV, CSVC, STRUCT):
            check = path.read_text(encoding="utf-8")
            if MARKER not in check:
                raise RuntimeError(f"Kiểm tra marker không đạt: {path}")

        # Kiểm tra không còn form.submit() trong hai đoạn cascade cũ.
        gv_check = GV.read_text(encoding="utf-8")
        csvc_check = CSVC.read_text(encoding="utf-8")
        if "safeScopeSubmit()" not in gv_check or "safeScopeSubmit()" not in csvc_check:
            raise RuntimeError("Kiểm tra submit an toàn chưa đạt.")

        print("")
        print("ĐÃ SỬA:")
        print(" - Đội ngũ MN-01-GV: Xã/phường -> nạp lại danh sách trường.")
        print(" - CSVC MN-01-CSVC: Xã/phường -> nạp lại danh sách trường.")
        print(" - TH-01-GV / TH-01-CSVC: áp dụng cùng cơ chế.")
        print(" - THCS-01-GV / THCS-01-CSVC: áp dụng cùng cơ chế.")
        print("")
        print("NGUYÊN NHÂN ĐÃ XỬ LÝ:")
        print(' - Không còn URL dạng &school_id=')
        print(' - Chỉ thêm school_id khi thực sự đã có ID trường.')
        print("")
        print("GIỮ NGUYÊN:")
        print(" - Toàn bộ dữ liệu hiện có")
        print(" - Database")
        print(" - Menu 3 cấp")
        print(" - Báo cáo")
        print(" - Điều tra hộ dân và giao diện điện thoại")
        print("")
        print("CAI DAT BAI 13B-6 V1.1 THANH CONG")
        print("Backup:", BACKUP)
        return 0

    except Exception:
        traceback.print_exc()
        _restore(manifest)
        print("")
        print("CÓ LỖI - ĐÃ KHÔI PHỤC 3 TEMPLATE TỰ ĐỘNG.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
