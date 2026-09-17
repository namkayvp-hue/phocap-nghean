# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import py_compile
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

YEAR_TEMPLATE = ROOT / "app" / "templates" / "surveys" / "year_records.html"
SURVEYS_ROUTER = ROOT / "app" / "routers" / "surveys.py"
MN_TEMPLATE_ROUTER = ROOT / "app" / "routers" / "pcgdmn_template_report.py"
REPORT_CENTER = ROOT / "app" / "routers" / "report_center.py"
BUSINESS_RULES = ROOT / "app" / "services" / "pcgd_business_rules.py"

BACKUP_DIR = ROOT / "backups"
EXPORT_DIR = ROOT / "exports"
OUT = EXPORT_DIR / "BATCH_SUA_MN01_NOI_HOC_VA_THM1_PHAN_TRAM_22.txt"

EXPECTED_DB_SHA = "2a43e36ff8f192abb46668faa1366ed7242984bfd876f90572cd83b90ee7837e"

MARK_UI = "BATCH22_STUDY_LOCATION_SPLIT"
MARK_SAVE = "BATCH22_STUDY_LOCATION_SAVE"
MARK_MN = "BATCH22_MN01_LOCATION_SCOPE"
MARK_TH = "BATCH22_TH_M1_PERCENT_DISPLAY"
MARK_RULE = "BATCH22_LOCATION_SEMANTICS"


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
        raise RuntimeError(
            "DB SHA khác nền đã chốt. Dừng để không sửa source trên nền dữ liệu khác."
        )

    con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True, timeout=30)
    try:
        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
        fk = con.execute("PRAGMA foreign_key_check").fetchall()
        cols = {
            r[1]
            for r in con.execute(
                'PRAGMA table_info("survey_person_year_records")'
            ).fetchall()
        }
    finally:
        con.close()

    if integrity != "ok" or fk:
        raise RuntimeError(
            f"Database health không đạt: integrity={integrity}, fk={len(fk)}"
        )

    required_cols = {
        "study_location_scope",
        "school_commune_name_reported",
        "school_province_name_reported",
    }
    missing = sorted(required_cols - cols)
    if missing:
        raise RuntimeError(
            f"Thiếu cột DB đã được Batch 21 xác nhận: {missing}"
        )

    return sha, integrity, len(fk)


def backup_files(paths: list[Path], backup_root: Path):
    result = {}
    for path in paths:
        if not path.exists():
            raise RuntimeError(f"Không tìm thấy source bắt buộc: {path}")
        rel = path.relative_to(ROOT)
        dst = backup_root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dst)
        result[path] = dst
    return result


def restore_files(backups: dict[Path, Path]):
    for target, backup in backups.items():
        if backup.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup, target)


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(
            f"{label}: cần đúng 1 khối nền để thay, thực tế count={count}."
        )
    return text.replace(old, new, 1)


def patch_year_template(text: str) -> tuple[str, str]:
    if MARK_UI in text:
        return text, "ALREADY_PRESENT"

    old = '''                <option
                    value="DI_HOC_NOI_KHAC"
                    {% if b1512_location == "DI_HOC_NOI_KHAC" %}selected{% endif %}
                >
                    Đi học nơi khác
                </option>'''

    new = '''                {# BATCH22_STUDY_LOCATION_SPLIT #}
                <option
                    value="DI_HOC_TRONG_TINH"
                    {% if b1512_location == "DI_HOC_TRONG_TINH" %}selected{% endif %}
                >
                    Đi học nơi khác – Trong tỉnh
                </option>

                <option
                    value="DI_HOC_NGOAI_TINH"
                    {% if b1512_location == "DI_HOC_NGOAI_TINH" %}selected{% endif %}
                >
                    Đi học nơi khác – Ngoài tỉnh
                </option>

                <option
                    value="DI_HOC_NOI_KHAC"
                    {% if b1512_location == "DI_HOC_NOI_KHAC" %}selected{% endif %}
                >
                    Đi học nơi khác – Chưa phân loại (dữ liệu cũ)
                </option>
                {# END BATCH22_STUDY_LOCATION_SPLIT #}'''

    return replace_once(
        text, old, new,
        "year_records.html / lựa chọn Đi học nơi khác"
    ), "PATCHED"


def patch_surveys_router(text: str) -> tuple[str, str]:
    if MARK_SAVE in text:
        return text, "ALREADY_PRESENT"

    old = '''            if _b1512_location not in {
                "CHUA_XAC_DINH",
                "TAI_CHO",
                "DI_HOC_NOI_KHAC",
                "NOI_KHAC_DEN",
            }:'''

    new = '''            # BATCH22_STUDY_LOCATION_SAVE
            if _b1512_location not in {
                "CHUA_XAC_DINH",
                "TAI_CHO",
                "DI_HOC_TRONG_TINH",
                "DI_HOC_NGOAI_TINH",
                "DI_HOC_NOI_KHAC",
                "NOI_KHAC_DEN",
            }:'''

    return replace_once(
        text, old, new,
        "surveys.py / whitelist study_location_scope"
    ), "PATCHED"


def patch_mn_template_router(text: str) -> tuple[str, str]:
    if MARK_MN in text:
        return text, "ALREADY_PRESENT"

    old = '''    code = str(row.get("study_location_scope") or "").strip().upper()
    if code in {"TAI_CHO", "TRONG_XA", "CUNG_XA"}:
        return True
    if code in {
        "KHAC_XA",
        "TRONG_TINH_KHAC_XA",
        "NGOAI_DIA_BAN",
        "TRAI_TUYEN",
    }:
        return False'''

    new = '''    # BATCH22_MN01_LOCATION_SCOPE
    # MN-01-TE: phân biệt nơi học TRONG TỈNH / NGOÀI TỈNH.
    # Không dùng biến động cư trú CHUYỂN ĐI để suy ra nơi học.
    code = str(row.get("study_location_scope") or "").strip().upper()

    if code == "DI_HOC_TRONG_TINH":
        return True
    if code == "DI_HOC_NGOAI_TINH":
        return False

    # Tương thích dữ liệu cũ trước Batch 22.
    if code in {"TAI_CHO", "TRONG_XA", "CUNG_XA"}:
        return True
    if code in {
        "KHAC_XA",
        "TRONG_TINH_KHAC_XA",
        "NGOAI_DIA_BAN",
        "TRAI_TUYEN",
        "DI_HOC_NOI_KHAC",
    }:
        return False'''

    return replace_once(
        text, old, new,
        "pcgdmn_template_report.py / phân loại nơi học"
    ), "PATCHED"


def patch_business_rules(text: str) -> tuple[str, str]:
    if MARK_RULE in text:
        return text, "ALREADY_PRESENT"

    old_primary = '''PRIMARY_LOCATION_SEMANTICS = {
    "TAI_CHO": "Có hộ khẩu tại xã, học tại trường Tiểu học trong xã.",
    "DI_HOC_NOI_KHAC": "Có hộ khẩu tại xã, học tại trường Tiểu học ngoài xã.",
    "NOI_KHAC_DEN": "Có hộ khẩu ngoài xã, đến học tại trường Tiểu học trong xã.",
}'''

    new_primary = '''# BATCH22_LOCATION_SEMANTICS
PRIMARY_LOCATION_SEMANTICS = {
    "TAI_CHO": "Có hộ khẩu tại xã, học tại trường Tiểu học trong xã.",
    "DI_HOC_TRONG_TINH": "Có hộ khẩu tại địa bàn, đi học nơi khác nhưng vẫn trong tỉnh.",
    "DI_HOC_NGOAI_TINH": "Có hộ khẩu tại địa bàn, đi học tại tỉnh/thành khác.",
    "DI_HOC_NOI_KHAC": "Dữ liệu cũ: đi học nơi khác nhưng chưa phân loại trong/ngoài tỉnh.",
    "NOI_KHAC_DEN": "Có hộ khẩu ngoài xã, đến học tại trường Tiểu học trong xã.",
}'''

    text = replace_once(
        text, old_primary, new_primary,
        "pcgd_business_rules.py / PRIMARY_LOCATION_SEMANTICS"
    )

    old_lower = '''LOWER_SECONDARY_LOCATION_SEMANTICS = {
    "TAI_CHO": "Có hộ khẩu tại xã, học/TN THCS tại trường THCS trong xã.",
    "DI_HOC_NOI_KHAC": "Có hộ khẩu tại xã, học/TN THCS tại trường THCS ngoài xã.",
    "NOI_KHAC_DEN": "Có hộ khẩu ngoài xã, đến học/TN THCS tại trường THCS trong xã.",
}'''

    new_lower = '''LOWER_SECONDARY_LOCATION_SEMANTICS = {
    "TAI_CHO": "Có hộ khẩu tại xã, học/TN THCS tại trường THCS trong xã.",
    "DI_HOC_TRONG_TINH": "Có hộ khẩu tại địa bàn, học/TN THCS nơi khác nhưng trong tỉnh.",
    "DI_HOC_NGOAI_TINH": "Có hộ khẩu tại địa bàn, học/TN THCS ở tỉnh/thành khác.",
    "DI_HOC_NOI_KHAC": "Dữ liệu cũ: học/TN THCS nơi khác nhưng chưa phân loại trong/ngoài tỉnh.",
    "NOI_KHAC_DEN": "Có hộ khẩu ngoài xã, đến học/TN THCS tại trường THCS trong xã.",
}'''

    text = replace_once(
        text, old_lower, new_lower,
        "pcgd_business_rules.py / LOWER_SECONDARY_LOCATION_SEMANTICS"
    )

    return text, "PATCHED"


def patch_th_m1(text: str) -> tuple[str, str]:
    if MARK_TH in text:
        return text, "ALREADY_PRESENT"

    old = '''    for result_ref, numerator_ref, denominator_refs in mappings:
        numerator = _b15245_cell_number(ws, numerator_ref)
        denominator = _b15245_sum_cells(ws, denominator_refs)
        ws[result_ref] = safe_percent(numerator, denominator)'''

    new = '''    for result_ref, numerator_ref, denominator_refs in mappings:
        numerator = _b15245_cell_number(ws, numerator_ref)
        denominator = _b15245_sum_cells(ws, denominator_refs)
        ws[result_ref] = safe_percent(numerator, denominator)

        # BATCH22_TH_M1_PERCENT_DISPLAY
        # safe_percent trả theo thang 0..100 (ví dụ 100.0).
        # Chỉ thêm ký hiệu % literal; KHÔNG dùng format 0.00%
        # vì format chuẩn Excel đó sẽ nhân tiếp 100 lần.
        ws[result_ref].number_format = r'0.00\\%' '''

    return replace_once(
        text, old, new,
        "report_center.py / TH-M1 tỷ lệ G40:G44"
    ), "PATCHED"


def compile_python(paths: list[Path]):
    for path in paths:
        py_compile.compile(str(path), doraise=True)


def verify_content():
    checks = {
        YEAR_TEMPLATE: [
            MARK_UI,
            'value="DI_HOC_TRONG_TINH"',
            'value="DI_HOC_NGOAI_TINH"',
            "Đi học nơi khác – Trong tỉnh",
            "Đi học nơi khác – Ngoài tỉnh",
        ],
        SURVEYS_ROUTER: [
            MARK_SAVE,
            '"DI_HOC_TRONG_TINH"',
            '"DI_HOC_NGOAI_TINH"',
        ],
        MN_TEMPLATE_ROUTER: [
            MARK_MN,
            'code == "DI_HOC_TRONG_TINH"',
            'code == "DI_HOC_NGOAI_TINH"',
        ],
        REPORT_CENTER: [
            MARK_TH,
            r"number_format = r'0.00\\%'",
        ],
        BUSINESS_RULES: [
            MARK_RULE,
            '"DI_HOC_TRONG_TINH"',
            '"DI_HOC_NGOAI_TINH"',
        ],
    }

    for path, needles in checks.items():
        text = path.read_text(encoding="utf-8")
        missing = [x for x in needles if x not in text]
        if missing:
            raise RuntimeError(
                f"Verify source thất bại tại {path}: thiếu {missing}"
            )


def main():
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    with OUT.open("w", encoding="utf-8-sig", newline="\n") as f:
        log(f, "=" * 160)
        log(f, "BATCH 22 - SỬA NƠI HỌC TRONG/NGOÀI TỈNH + MN-01-TE + TH-M1 TỶ LỆ %")
        log(f, "CHỈ SỬA SOURCE; KHÔNG TỰ CHUYỂN DỮ LIỆU CŨ; KHÔNG GHI DATABASE")
        log(f, "=" * 160)

        db_sha, integrity, fk_count = validate_db()
        log(f, "DB_SHA =", db_sha)
        log(f, "INTEGRITY =", integrity)
        log(f, "FK =", fk_count)

        paths = [
            YEAR_TEMPLATE,
            SURVEYS_ROUTER,
            MN_TEMPLATE_ROUTER,
            REPORT_CENTER,
            BUSINESS_RULES,
        ]

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_root = BACKUP_DIR / f"source_truoc_BATCH22_{ts}"
        backups = backup_files(paths, backup_root)
        log(f, "SOURCE_BACKUP_DIR =", backup_root)

        try:
            text = YEAR_TEMPLATE.read_text(encoding="utf-8")
            text, status = patch_year_template(text)
            YEAR_TEMPLATE.write_text(text, encoding="utf-8")
            log(f, "PATCH year_records.html =", status)

            text = SURVEYS_ROUTER.read_text(encoding="utf-8")
            text, status = patch_surveys_router(text)
            SURVEYS_ROUTER.write_text(text, encoding="utf-8")
            log(f, "PATCH surveys.py =", status)

            text = MN_TEMPLATE_ROUTER.read_text(encoding="utf-8")
            text, status = patch_mn_template_router(text)
            MN_TEMPLATE_ROUTER.write_text(text, encoding="utf-8")
            log(f, "PATCH pcgdmn_template_report.py =", status)

            text = REPORT_CENTER.read_text(encoding="utf-8")
            text, status = patch_th_m1(text)
            REPORT_CENTER.write_text(text, encoding="utf-8")
            log(f, "PATCH report_center.py =", status)

            text = BUSINESS_RULES.read_text(encoding="utf-8")
            text, status = patch_business_rules(text)
            BUSINESS_RULES.write_text(text, encoding="utf-8")
            log(f, "PATCH pcgd_business_rules.py =", status)

            compile_python([
                SURVEYS_ROUTER,
                MN_TEMPLATE_ROUTER,
                REPORT_CENTER,
                BUSINESS_RULES,
            ])
            log(f, "PY_COMPILE = PASS")

            verify_content()
            log(f, "SOURCE_VERIFY = PASS")

        except Exception:
            restore_files(backups)
            log(f, "ROLLBACK_SOURCE = PASS")
            raise

        log(f, "")
        log(f, "DB_SHA_AFTER =", sha256_file(DB))
        log(f, "DATABASE_WRITES_THIS_RUN = 0")
        log(f, "OLD_DATA_MIGRATION = 0")
        log(f, "BATCH_22_SUCCESS = YES")
        log(f, "")
        log(f, "TEST_1 = Mở 1 đối tượng điều tra -> Nơi học: phải có 'Trong tỉnh' và 'Ngoài tỉnh'.")
        log(f, "TEST_2 = Xuất MN-01-TE sau khi gán dữ liệu thử: mục nơi học phải tách theo lựa chọn mới.")
        log(f, "TEST_3 = Xuất TH-M1: G40:G44 phải hiển thị ví dụ 100,00% thay vì 100,00.")
        log(f, "NOTE = Mã DI_HOC_NOI_KHAC cũ vẫn giữ để không mất nghĩa dữ liệu lịch sử; không tự suy đoán thành trong/ngoài tỉnh.")
        log(f, "=" * 160)

    return 0


if __name__ == "__main__":
    try:
        rc = main()
    except Exception as exc:
        try:
            EXPORT_DIR.mkdir(parents=True, exist_ok=True)
            with OUT.open("a", encoding="utf-8-sig", newline="\n") as f:
                log(f, "")
                log(f, "=" * 160)
                log(f, "BATCH_22_SUCCESS = NO")
                log(f, "ERROR =", repr(exc))
                if DB.exists():
                    log(f, "DB_SHA_CURRENT =", sha256_file(DB))
                log(f, "DỪNG AN TOÀN.")
                log(f, "=" * 160)
        except Exception:
            print("ERROR =", repr(exc))
        rc = 1

    sys.exit(rc)
