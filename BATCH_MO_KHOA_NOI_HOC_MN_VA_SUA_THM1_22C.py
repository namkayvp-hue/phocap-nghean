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
REPORT_CENTER = ROOT / "app" / "routers" / "report_center.py"

BACKUP_DIR = ROOT / "backups"
EXPORT_DIR = ROOT / "exports"
OUT = EXPORT_DIR / "BATCH_MO_KHOA_NOI_HOC_MN_VA_SUA_THM1_22C.txt"

EXPECTED_DB_SHA = "2a43e36ff8f192abb46668faa1366ed7242984bfd876f90572cd83b90ee7837e"

MARK_UI = "BATCH22B_SHOW_STUDY_LOCATION_FOR_MN"
MARK_FIX = "BATCH22C_UNLOCK_STUDY_LOCATION_MN"
MARK_TH = "BATCH22B_TH_M1_FINAL_PERCENT_FORMAT"

OLD_UNLOCK = '            group.style.removeProperty("display");\n            group.hidden = false;'
NEW_UNLOCK = '            group.style.removeProperty("display");\n            group.hidden = false;\n\n            // BATCH22C_UNLOCK_STUDY_LOCATION_MN\n            // Logic cũ chỉ cho TH/THCS dùng Nơi học nên select vẫn bị disabled.\n            // Khi khối Mầm non đang hoạt động, mở select để giáo viên chọn.\n            const studySelect = group.querySelector("select");\n            if (studySelect) {\n                studySelect.disabled = false;\n                studySelect.removeAttribute("disabled");\n                studySelect.removeAttribute("aria-disabled");\n                studySelect.style.removeProperty("pointer-events");\n                studySelect.style.removeProperty("opacity");\n            }'


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def log(f, *parts):
    s = " ".join(str(x) for x in parts)
    print(s)
    f.write(s + "\n")
    f.flush()


def validate_db():
    sha = sha256_file(DB)
    if sha != EXPECTED_DB_SHA:
        raise RuntimeError("DB SHA khác nền đã chốt.")

    con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True, timeout=30)
    try:
        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
        fk = con.execute("PRAGMA foreign_key_check").fetchall()
    finally:
        con.close()

    if integrity != "ok" or fk:
        raise RuntimeError(
            f"Database health không đạt: integrity={integrity}, fk={len(fk)}"
        )

    return sha, integrity, len(fk)


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: cần đúng 1 khối, count={count}")
    return text.replace(old, new, 1)


def patch_year_template(text: str):
    if MARK_UI not in text:
        raise RuntimeError(
            "Chưa có Batch 22B trong year_records.html; không vá nối tiếp."
        )

    statuses = []

    if MARK_FIX not in text:
        text = replace_once(
            text,
            OLD_UNLOCK,
            NEW_UNLOCK,
            "year_records / unlock study location"
        )
        statuses.append("UNLOCK_ADDED")
    else:
        statuses.append("UNLOCK_ALREADY_PRESENT")

    old_filter = 'attributeFilter: ["style", "class", "hidden"]'
    new_filter = 'attributeFilter: ["style", "class", "hidden", "disabled", "aria-disabled"]'

    if old_filter in text:
        text = text.replace(old_filter, new_filter, 1)
        statuses.append("OBSERVER_DISABLED_ADDED")
    elif new_filter in text:
        statuses.append("OBSERVER_ALREADY_PRESENT")
    else:
        raise RuntimeError("Không tìm thấy attributeFilter của Batch 22B.")

    return text, "+".join(statuses)


def patch_th_m1(text: str):
    if MARK_TH not in text:
        raise RuntimeError(
            "Chưa có Batch 22B final percent format trong report_center.py."
        )

    statuses = []

    old_final = "ws[_percent_ref].number_format = r'0.00\\%'"
    new_final = "ws[_percent_ref].number_format = r'0\\%'"

    if old_final in text:
        text = text.replace(old_final, new_final, 1)
        statuses.append("FINAL_PERCENT_CHANGED_TO_INTEGER")
    elif new_final in text:
        statuses.append("FINAL_PERCENT_ALREADY_INTEGER")
    else:
        raise RuntimeError("Không tìm thấy format final G40:G44 của Batch 22B.")

    old_helper = "ws[result_ref].number_format = r'0.00\\%'"
    new_helper = "ws[result_ref].number_format = r'0\\%'"
    if old_helper in text:
        text = text.replace(old_helper, new_helper)
        statuses.append("HELPER_PERCENT_CHANGED_TO_INTEGER")

    return text, "+".join(statuses)


def main():
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    with OUT.open("w", encoding="utf-8-sig", newline="\n") as f:
        log(f, "=" * 160)
        log(f, "BATCH 22C - MỞ KHÓA NƠI HỌC MẦM NON + SỬA #### Ở TH-M1")
        log(f, "CHỈ SỬA SOURCE; KHÔNG GHI DATABASE")
        log(f, "=" * 160)

        sha, integrity, fk_count = validate_db()
        log(f, "DB_SHA =", sha)
        log(f, "INTEGRITY =", integrity)
        log(f, "FK =", fk_count)

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_root = BACKUP_DIR / f"source_truoc_BATCH22C_{ts}"
        backup_root.mkdir(parents=True, exist_ok=True)

        backups = {}
        for p in (YEAR_TEMPLATE, REPORT_CENTER):
            if not p.exists():
                raise RuntimeError(f"Không tìm thấy source: {p}")
            dst = backup_root / p.relative_to(ROOT)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, dst)
            backups[p] = dst

        log(f, "SOURCE_BACKUP_DIR =", backup_root)

        try:
            text = YEAR_TEMPLATE.read_text(encoding="utf-8")
            text, status = patch_year_template(text)
            YEAR_TEMPLATE.write_text(text, encoding="utf-8")
            log(f, "PATCH Nơi học MN =", status)

            text = REPORT_CENTER.read_text(encoding="utf-8")
            text, status = patch_th_m1(text)
            REPORT_CENTER.write_text(text, encoding="utf-8")
            log(f, "PATCH TH-M1 =", status)

            py_compile.compile(str(REPORT_CENTER), doraise=True)
            log(f, "PY_COMPILE = PASS")

            verify_template = YEAR_TEMPLATE.read_text(encoding="utf-8")
            if MARK_FIX not in verify_template:
                raise RuntimeError("Verify: chưa có marker mở khóa Nơi học.")
            if "studySelect.disabled = false;" not in verify_template:
                raise RuntimeError("Verify: chưa có lệnh mở disabled.")
            if '"disabled", "aria-disabled"' not in verify_template:
                raise RuntimeError("Verify: observer chưa theo dõi disabled.")

            verify_report = REPORT_CENTER.read_text(encoding="utf-8")
            if "ws[_percent_ref].number_format = r'0\\%'" not in verify_report:
                raise RuntimeError("Verify: TH-M1 final format chưa là 0\\%.")

            log(f, "SOURCE_VERIFY = PASS")

        except Exception:
            for target, backup in backups.items():
                shutil.copy2(backup, target)
            log(f, "ROLLBACK_SOURCE = PASS")
            raise

        log(f, "DB_SHA_AFTER =", sha256_file(DB))
        log(f, "DATABASE_WRITES_THIS_RUN = 0")
        log(f, "BATCH_22C_SUCCESS = YES")
        log(f, "")
        log(f, "TEST_1 = Khởi động lại Uvicorn + Ctrl+F5. Nơi học của trẻ Mầm non phải bấm/chọn được.")
        log(f, "TEST_2 = Chọn thử Trong tỉnh hoặc Ngoài tỉnh rồi Lưu.")
        log(f, "TEST_3 = Xuất lại TH-M1 mới. G40:G44 phải hiện 100%/0% thay vì ######.")
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
                log(f, "BATCH_22C_SUCCESS = NO")
                log(f, "ERROR =", repr(exc))
                if DB.exists():
                    log(f, "DB_SHA_CURRENT =", sha256_file(DB))
                log(f, "DỪNG AN TOÀN.")
                log(f, "=" * 160)
        except Exception:
            print("ERROR =", repr(exc))
        rc = 1

    sys.exit(rc)
