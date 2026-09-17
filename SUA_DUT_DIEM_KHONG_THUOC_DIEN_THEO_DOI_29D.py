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
APP = ROOT / "app"
DB = ROOT / "data" / "phocap.db"
YEAR = APP / "templates" / "surveys" / "year_records.html"

EXPORTS = ROOT / "exports"
BACKUPS = ROOT / "backups"
OUT = EXPORTS / "SUA_DUT_DIEM_KHONG_THUOC_DIEN_THEO_DOI_29D.txt"

START = "<!-- === BAI29B_SAFE_AUTO_NOT_TRACKED_START === -->"
END = "<!-- === BAI29B_SAFE_AUTO_NOT_TRACKED_END === -->"
NEW_BLOCK = '<!-- === BAI29B_SAFE_AUTO_NOT_TRACKED_START === -->\n<style>\n    .b29b-auto-note {\n        margin-top: 7px;\n        padding: 8px 10px;\n        border-radius: 9px;\n        background: #eef8f1;\n        color: #245b35;\n        font-size: 13px;\n        line-height: 1.45;\n    }\n</style>\n\n<script>\n(function () {\n    "use strict";\n\n    const birthDateRaw = "{{ person.date_of_birth or \'\' }}";\n    const savedLearningStatus =\n        "{{ selected_record.learning_status if selected_record and selected_record.learning_status else \'\' }}";\n\n    function selectedSchoolYearStart() {\n        const bodyText = document.body\n            ? (document.body.innerText || "")\n            : "";\n        const match = bodyText.match(/\\b(20\\d{2})\\s*[-–]\\s*(20\\d{2})\\b/);\n        return match ? Number(match[1]) : null;\n    }\n\n    function ageAtSeptember30() {\n        const match = String(birthDateRaw).match(\n            /^(\\d{4})-(\\d{2})-(\\d{2})/\n        );\n        const startYear = selectedSchoolYearStart();\n\n        if (!match || !startYear) return null;\n\n        const birthYear = Number(match[1]);\n        const birthMonth = Number(match[2]);\n        const birthDay = Number(match[3]);\n\n        let age = startYear - birthYear;\n\n        if (\n            birthMonth > 9\n            || (birthMonth === 9 && birthDay > 30)\n        ) {\n            age -= 1;\n        }\n        return age;\n    }\n\n    function fieldValue(id) {\n        const element = document.getElementById(id);\n        return element\n            ? String(element.value || "").trim()\n            : "";\n    }\n\n    function hasCurrentSchoolOrClass() {\n        return Boolean(\n            fieldValue("school_id")\n            || fieldValue("class_id")\n            || fieldValue("school_name_reported")\n            || fieldValue("class_name_reported")\n        );\n    }\n\n    function ensureOption(select) {\n        if (!select) return false;\n\n        const existing = Array.from(select.options).find(\n            option => option.value === "KHONG_THUOC_DIEN"\n        );\n        if (existing) return true;\n\n        const option = document.createElement("option");\n        option.value = "KHONG_THUOC_DIEN";\n        option.textContent = "Không thuộc diện theo dõi";\n        select.appendChild(option);\n        return true;\n    }\n\n    function showNote(select, age) {\n        if (!select) return;\n\n        let note = document.getElementById("b29b_auto_note");\n        if (!note) {\n            note = document.createElement("div");\n            note.id = "b29b_auto_note";\n            note.className = "b29b-auto-note";\n            select.insertAdjacentElement("afterend", note);\n        }\n\n        note.textContent =\n            "Hệ thống xác định “Không thuộc diện theo dõi” vì đối tượng "\n            + age\n            + " tuổi tại thời điểm 30/9 của năm học và không có trường/lớp "\n            + "hiện tại. Phần Xóa mù chữ vẫn được theo dõi độc lập.";\n    }\n\n    function hideNote() {\n        const note = document.getElementById("b29b_auto_note");\n        if (note) note.remove();\n    }\n\n    function applySafeDefault() {\n        const select = document.getElementById("learning_status");\n        if (!select) return;\n\n        const age = ageAtSeptember30();\n        if (age === null) return;\n\n        const saved = String(savedLearningStatus || "")\n            .trim()\n            .toUpperCase();\n\n        if (age > 18 && !hasCurrentSchoolOrClass()) {\n            const allowedToCorrect = new Set([\n                "",\n                "CHUA_XAC_DINH",\n                "DANG_HOC",\n                "KHONG_THUOC_DIEN"\n            ]);\n\n            if (!allowedToCorrect.has(saved)) {\n                hideNote();\n                return;\n            }\n\n            if (!ensureOption(select)) return;\n\n            if (select.value !== "KHONG_THUOC_DIEN") {\n                select.value = "KHONG_THUOC_DIEN";\n            }\n\n            showNote(select, age);\n            return;\n        }\n\n        hideNote();\n    }\n\n    function scheduleApply() {\n        [0, 150, 400, 900, 1600].forEach(function (ms) {\n            window.setTimeout(applySafeDefault, ms);\n        });\n    }\n\n    document.addEventListener("DOMContentLoaded", scheduleApply);\n    window.addEventListener("pageshow", scheduleApply);\n\n    ["school_id", "class_id", "school_name_reported", "class_name_reported"]\n        .forEach(function (id) {\n            document.addEventListener(\n                "change",\n                function (event) {\n                    if (event.target && event.target.id === id) {\n                        scheduleApply();\n                    }\n                },\n                true\n            );\n\n            document.addEventListener(\n                "input",\n                function (event) {\n                    if (event.target && event.target.id === id) {\n                        scheduleApply();\n                    }\n                },\n                true\n            );\n        });\n})();\n</script>\n<!-- === BAI29B_SAFE_AUTO_NOT_TRACKED_END === -->'


def log(f, *parts):
    line = " ".join(str(x) for x in parts)
    print(line)
    f.write(line + "\n")
    f.flush()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as src:
        for block in iter(lambda: src.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def db_health():
    con = sqlite3.connect(
        f"file:{DB.as_posix()}?mode=ro",
        uri=True,
        timeout=30,
    )
    try:
        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
        fk = con.execute("PRAGMA foreign_key_check").fetchall()
        row79 = con.execute(
            "SELECT p.id, p.full_name, p.date_of_birth, "
            "y.learning_status, y.school_id, y.class_id, "
            "y.school_name_reported, y.class_name_reported "
            "FROM survey_people p "
            "LEFT JOIN survey_person_year_records y "
            "ON y.survey_person_id = p.id AND y.school_year_id = 2 "
            "WHERE p.id = 79 LIMIT 1"
        ).fetchone()
    finally:
        con.close()

    if integrity != "ok" or fk:
        raise RuntimeError(
            f"DB health không đạt: integrity={integrity}; FK={len(fk)}"
        )
    return integrity, len(fk), row79


def clear_cache():
    for cache in APP.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)


def verify_preserved(before: str, after: str):
    protected = [
        'name="learning_status"',
        'name="is_literacy_target"',
        'name="completed_grade_3"',
        'name="completed_grade_5"',
        'name="highest_completed_grade"',
        'name="education_attainment_level"',
        'name="study_location_scope"',
        'name="disability_status"',
        'name="completed_preschool_by_age"',
        'name="completed_primary_program"',
        'name="completed_lower_secondary_program"',
    ]
    changed = []
    for token in protected:
        b = before.count(token)
        a = after.count(token)
        if a != b:
            changed.append((token, b, a))
    if changed:
        raise RuntimeError(
            "Bài 29D làm thay đổi control nghiệp vụ đang chạy: "
            + repr(changed)
        )


def main():
    EXPORTS.mkdir(parents=True, exist_ok=True)
    BACKUPS.mkdir(parents=True, exist_ok=True)

    with OUT.open("w", encoding="utf-8-sig", newline="\n") as f:
        log(f, "=" * 170)
        log(f, "BÀI 29D - SỬA DỨT ĐIỂM 'KHÔNG THUỘC DIỆN THEO DÕI'")
        log(f, "CHỈ THAY BLOCK JS BÀI 29B/29C - KHÔNG ĐỤNG BACKEND - KHÔNG GHI DB")
        log(f, "=" * 170)

        for p in (DB, YEAR):
            if not p.exists():
                raise RuntimeError(f"Không tìm thấy: {p}")

        integrity, fk_count, row79 = db_health()
        db_sha_before = sha256_file(DB)

        log(f, "DB_SHA_BEFORE =", db_sha_before)
        log(f, "INTEGRITY =", integrity)
        log(f, "FK_COUNT =", fk_count)
        log(f, "PERSON_79_DB =", row79)

        before = YEAR.read_text(encoding="utf-8-sig")

        if START not in before or END not in before:
            raise RuntimeError(
                "Không tìm thấy block Bài 29B/29C. Dừng để tránh sửa nhầm."
            )

        start = before.index(START)
        end = before.index(END, start) + len(END)

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_root = BACKUPS / f"source_truoc_BAI29D_{stamp}"
        backup_file = backup_root / YEAR.relative_to(ROOT)
        backup_file.parent.mkdir(parents=True, exist_ok=False)
        shutil.copy2(YEAR, backup_file)
        log(f, "SOURCE_BACKUP =", backup_root)

        try:
            after = before[:start] + NEW_BLOCK + before[end:]
            verify_preserved(before, after)

            if "</body>" not in after:
                raise RuntimeError("Template không còn </body>.")

            YEAR.write_text(after, encoding="utf-8")
            clear_cache()

            check = YEAR.read_text(encoding="utf-8")
            if "allowedToCorrect" not in check:
                raise RuntimeError("Block 29D chưa được ghi đúng.")
            if "[0, 150, 400, 900, 1600]" not in check:
                raise RuntimeError("Block 29D chưa có lịch áp dụng nhiều thời điểm.")
            if 'name="learning_status"' not in check:
                raise RuntimeError("Mất control learning_status.")

            log(f, "PATCH_SCOPE = ONLY_BAI29_BLOCK")
            log(f, "PROTECTED_CONTROLS = PASS")
            log(f, "BACKEND_CHANGE = NONE")
            log(f, "SOURCE_VERIFY = PASS")

        except Exception:
            shutil.copy2(backup_file, YEAR)
            clear_cache()
            log(f, "ROLLBACK_SOURCE = PASS")
            raise

        db_sha_after = sha256_file(DB)
        if db_sha_after != db_sha_before:
            shutil.copy2(backup_file, YEAR)
            clear_cache()
            raise RuntimeError(
                "DB thay đổi trong lúc cài source; đã rollback template."
            )

        log(f, "DB_SHA_AFTER =", db_sha_after)
        log(f, "DATABASE_WRITES_THIS_RUN = 0")
        log(f, "BAI29D_SUCCESS = YES")
        log(f, "")
        log(f, "LOGIC_29D:")
        log(f, " - Tuổi >18 và không có trường/lớp:")
        log(f, "   DB trống/CHUA_XAC_DINH/DANG_HOC/KHONG_THUOC_DIEN")
        log(f, "   => giao diện chọn KHONG_THUOC_DIEN.")
        log(f, " - Các trạng thái nghiệp vụ khác đã lưu vẫn giữ nguyên.")
        log(f, " - Không tự POST; người dùng vẫn bấm Lưu theo luồng cũ.")
        log(f, " - XMC và các nghiệp vụ đã làm được không thay đổi.")
        log(f, "=" * 170)

    return 0


if __name__ == "__main__":
    try:
        rc = main()
    except Exception as exc:
        try:
            EXPORTS.mkdir(parents=True, exist_ok=True)
            with OUT.open("a", encoding="utf-8-sig", newline="\n") as f:
                log(f, "")
                log(f, "=" * 170)
                log(f, "BAI29D_SUCCESS = NO")
                log(f, "ERROR =", repr(exc))
                if DB.exists():
                    log(f, "DB_SHA_CURRENT =", sha256_file(DB))
                log(f, "DỪNG AN TOÀN.")
                log(f, "=" * 170)
        except Exception:
            print("ERROR =", repr(exc))
        rc = 1

    raise SystemExit(rc)
