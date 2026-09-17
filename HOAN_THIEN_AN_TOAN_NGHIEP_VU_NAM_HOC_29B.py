# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
import hashlib
import py_compile
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
APP = ROOT / "app"
DB = ROOT / "data" / "phocap.db"
SURVEYS = APP / "routers" / "surveys.py"
YEAR = APP / "templates" / "surveys" / "year_records.html"

BACKUPS = ROOT / "backups"
EXPORTS = ROOT / "exports"
OUT = EXPORTS / "HOAN_THIEN_AN_TOAN_NGHIEP_VU_NAM_HOC_29B.txt"

START = "<!-- === BAI29B_SAFE_AUTO_NOT_TRACKED_START === -->"
END = "<!-- === BAI29B_SAFE_AUTO_NOT_TRACKED_END === -->"

LOCKED_WORKING_TOKENS = ['name="learning_status"', 'name="school_id"', 'name="class_id"', 'name="school_name_reported"', 'name="class_name_reported"', 'name="highest_completed_grade"', 'name="education_attainment_level"', 'name="is_literacy_target"', 'name="completed_grade_3"', 'name="completed_grade_5"', 'name="residency_status"', 'name="move_in_date"', 'name="move_in_origin"', 'name="move_out_date"', 'name="move_out_destination"', 'name="death_date"', 'name="study_location_scope"', 'name="disability_status"', 'name="disability_type"', 'name="disability_level"', 'name="disability_certificate"', 'name="inclusive_education"', 'name="disability_support"', 'name="disability_support_details"', 'name="disability_can_learn"', 'name="disability_access_education"', 'name="completed_preschool_by_age"', 'name="attends_two_sessions_per_day"', 'name="prepared_vietnamese"', 'name="completed_primary_program"', 'name="completed_lower_secondary_program"', 'name="post_lower_secondary_path"', 'name="is_repeating_grade"', 'name="current_education_program"']

DO_NOT_RESTORE_AUTOMATICALLY = ['literacy_status', 'completed_preschool_5', 'attends_required_days', 'attends_regularly', 'weight_monitored', 'underweight', 'height_monitored', 'stunted', 'school_commune_name_reported', 'school_province_name_reported']

BLOCK = '\n<!-- === BAI29B_SAFE_AUTO_NOT_TRACKED_START === -->\n<style>\n    .b29b-auto-note {\n        margin-top: 7px;\n        padding: 8px 10px;\n        border-radius: 9px;\n        background: #eef8f1;\n        color: #245b35;\n        font-size: 13px;\n        line-height: 1.45;\n    }\n</style>\n\n<script>\n(function () {\n    "use strict";\n\n    const birthDateRaw = "{{ person.date_of_birth or \'\' }}";\n\n    function selectedSchoolYearStart() {\n        const selectedOptions = Array.from(\n            document.querySelectorAll("select option:checked")\n        );\n\n        for (const option of selectedOptions) {\n            const text = (option.textContent || "").trim();\n            const match = text.match(/\\b(20\\d{2})\\s*[-–]\\s*(20\\d{2})\\b/);\n            if (match) {\n                return Number(match[1]);\n            }\n        }\n\n        const bodyText = document.body\n            ? (document.body.innerText || "")\n            : "";\n        const fallback = bodyText.match(/\\b(20\\d{2})\\s*[-–]\\s*(20\\d{2})\\b/);\n        return fallback ? Number(fallback[1]) : null;\n    }\n\n    function ageAtSeptember30() {\n        const match = String(birthDateRaw).match(\n            /^(\\d{4})-(\\d{2})-(\\d{2})/\n        );\n        const startYear = selectedSchoolYearStart();\n\n        if (!match || !startYear) return null;\n\n        const birthYear = Number(match[1]);\n        const birthMonth = Number(match[2]);\n        const birthDay = Number(match[3]);\n\n        let age = startYear - birthYear;\n        if (\n            birthMonth > 9\n            || (birthMonth === 9 && birthDay > 30)\n        ) {\n            age -= 1;\n        }\n        return age;\n    }\n\n    function hasCurrentSchoolOrClass() {\n        const school = document.getElementById("school_id");\n        const classroom = document.getElementById("class_id");\n        const schoolReported =\n            document.getElementById("school_name_reported");\n        const classReported =\n            document.getElementById("class_name_reported");\n\n        return Boolean(\n            (school && String(school.value || "").trim())\n            || (classroom && String(classroom.value || "").trim())\n            || (\n                schoolReported\n                && String(schoolReported.value || "").trim()\n            )\n            || (\n                classReported\n                && String(classReported.value || "").trim()\n            )\n        );\n    }\n\n    function ensureOption(select) {\n        if (!select) return false;\n\n        const existing = Array.from(select.options).find(\n            option => option.value === "KHONG_THUOC_DIEN"\n        );\n        if (existing) return true;\n\n        const option = document.createElement("option");\n        option.value = "KHONG_THUOC_DIEN";\n        option.textContent = "Không thuộc diện theo dõi";\n        select.appendChild(option);\n        return true;\n    }\n\n    function showNote(select, age) {\n        if (!select || document.getElementById("b29b_auto_note")) {\n            return;\n        }\n\n        const note = document.createElement("div");\n        note.id = "b29b_auto_note";\n        note.className = "b29b-auto-note";\n        note.textContent =\n            "Hệ thống tự chọn “Không thuộc diện theo dõi” vì đối tượng "\n            + age\n            + " tuổi tại thời điểm 30/9 của năm học và chưa có trường/lớp "\n            + "hiện tại. Phần Xóa mù chữ vẫn được xác định riêng. "\n            + "Có thể đổi lại nếu thực tế đối tượng vẫn đang học.";\n        select.insertAdjacentElement("afterend", note);\n    }\n\n    function applySafeDefault() {\n        const select = document.getElementById("learning_status");\n        if (!select) return;\n\n        const age = ageAtSeptember30();\n        if (age === null || age <= 18) return;\n        if (hasCurrentSchoolOrClass()) return;\n\n        const current = String(select.value || "").trim().toUpperCase();\n        if (current && current !== "CHUA_XAC_DINH") {\n            return;\n        }\n\n        if (!ensureOption(select)) return;\n\n        select.value = "KHONG_THUOC_DIEN";\n        showNote(select, age);\n    }\n\n    document.addEventListener(\n        "DOMContentLoaded",\n        function () {\n            window.setTimeout(applySafeDefault, 250);\n\n            [\n                "school_id",\n                "class_id",\n                "school_name_reported",\n                "class_name_reported"\n            ].forEach(function (id) {\n                const element = document.getElementById(id);\n                if (!element) return;\n\n                element.addEventListener(\n                    "change",\n                    function () {\n                        window.setTimeout(applySafeDefault, 0);\n                    }\n                );\n                element.addEventListener(\n                    "input",\n                    function () {\n                        window.setTimeout(applySafeDefault, 0);\n                    }\n                );\n            });\n        }\n    );\n})();\n</script>\n<!-- === BAI29B_SAFE_AUTO_NOT_TRACKED_END === -->\n'


def log(f, *parts):
    line = " ".join(str(x) for x in parts)
    print(line)
    f.write(line + "\n")
    f.flush()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as src:
        for chunk in iter(lambda: src.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def db_check():
    con = sqlite3.connect(
        f"file:{DB.as_posix()}?mode=ro",
        uri=True,
        timeout=30,
    )
    try:
        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
        fk = con.execute("PRAGMA foreign_key_check").fetchall()
        learning = con.execute(
            "SELECT COALESCE(learning_status,'<NULL>'), COUNT(*) "
            "FROM survey_person_year_records "
            "WHERE school_year_id=2 "
            "GROUP BY COALESCE(learning_status,'<NULL>') "
            "ORDER BY COUNT(*) DESC"
        ).fetchall()
    finally:
        con.close()

    if integrity != "ok" or fk:
        raise RuntimeError(
            f"DB health không đạt: integrity={integrity}; FK={len(fk)}"
        )
    return integrity, len(fk), learning


def remove_old_block(text: str) -> str:
    pattern = re.compile(
        re.escape(START) + r".*?" + re.escape(END),
        flags=re.S,
    )
    return pattern.sub("", text)


def verify_working_tokens(before: str, after: str):
    missing_before = [x for x in LOCKED_WORKING_TOKENS if x not in before]
    if missing_before:
        raise RuntimeError(
            "Nền hiện tại đã thiếu nghiệp vụ đang khóa; "
            "FIX29B không được tự sửa tiếp: " + repr(missing_before)
        )

    missing_after = [x for x in LOCKED_WORKING_TOKENS if x not in after]
    if missing_after:
        raise RuntimeError(
            "FIX29B làm mất nghiệp vụ đang chạy: " + repr(missing_after)
        )

    changed = []
    for token in LOCKED_WORKING_TOKENS:
        b = before.count(token)
        a = after.count(token)
        if a != b:
            changed.append((token, b, a))
    if changed:
        raise RuntimeError(
            "FIX29B thay đổi số lượng control đang chạy: " + repr(changed)
        )


def verify_backend(source: str):
    ast.parse(source)
    required = [
        '"KHONG_THUOC_DIEN": "Không thuộc diện theo dõi"',
        "def luu_theo_doi_nam_hoc(",
        "record.learning_status = learning_status",
    ]
    missing = [x for x in required if x not in source]
    if missing:
        raise RuntimeError(
            "Backend Tình trạng học tập không còn đúng nền Bài 29: "
            + repr(missing)
        )


def jinja_verify(text: str):
    from jinja2 import Environment
    Environment().parse(text)


def clear_cache():
    for cache in APP.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)


def main():
    EXPORTS.mkdir(parents=True, exist_ok=True)
    BACKUPS.mkdir(parents=True, exist_ok=True)

    with OUT.open("w", encoding="utf-8-sig", newline="\n") as f:
        log(f, "=" * 170)
        log(f, "BÀI 29B - HOÀN THIỆN AN TOÀN NGHIỆP VỤ NĂM HỌC")
        log(f, "NGUYÊN TẮC: KHÔNG ĐỤNG CÁC NGHIỆP VỤ BÀI 29 XÁC NHẬN ĐANG CHẠY")
        log(f, "CHỈ BỔ SUNG MẶC ĐỊNH 'KHÔNG THUỘC DIỆN THEO DÕI' CHO TRƯỜNG HỢP RÕ RÀNG")
        log(f, "SOURCE ONLY - KHÔNG GHI DATABASE")
        log(f, "=" * 170)

        for p in (DB, SURVEYS, YEAR):
            if not p.exists():
                raise RuntimeError(f"Không tìm thấy: {p}")

        integrity, fk_count, learning_counts = db_check()
        db_sha_before = sha256_file(DB)

        log(f, "DB_SHA_BEFORE =", db_sha_before)
        log(f, "INTEGRITY =", integrity)
        log(f, "FK_COUNT =", fk_count)
        log(f, "LEARNING_STATUS_COUNTS =", learning_counts)

        source = SURVEYS.read_text(encoding="utf-8-sig")
        before = YEAR.read_text(encoding="utf-8-sig")

        verify_backend(source)
        verify_working_tokens(before, before)

        if "</body>" not in before:
            raise RuntimeError("year_records.html không có </body>.")

        log(
            f,
            "CHECK_FIELDS_NOT_AUTO_RESTORED =",
            DO_NOT_RESTORE_AUTOMATICALLY,
        )

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_root = BACKUPS / f"source_truoc_BAI29B_{stamp}"
        backup_file = backup_root / YEAR.relative_to(ROOT)
        backup_file.parent.mkdir(parents=True, exist_ok=False)
        shutil.copy2(YEAR, backup_file)
        log(f, "SOURCE_BACKUP =", backup_root)

        try:
            cleaned = remove_old_block(before)
            after = cleaned.replace(
                "</body>",
                BLOCK.strip() + "\n</body>",
                1,
            )

            verify_working_tokens(before, after)
            jinja_verify(after)

            YEAR.write_text(after, encoding="utf-8")
            clear_cache()

            py_compile.compile(str(SURVEYS), doraise=True)

            current = YEAR.read_text(encoding="utf-8")
            verify_working_tokens(before, current)
            if START not in current or END not in current:
                raise RuntimeError("Không tìm thấy block Bài 29B sau khi ghi.")

            log(f, "BACKEND_CHANGE = NONE")
            log(
                f,
                "WORKING_FEATURE_TOKENS_PRESERVED =",
                len(LOCKED_WORKING_TOKENS),
            )
            log(f, "JINJA_VERIFY = PASS")
            log(f, "PY_COMPILE_SURVEYS = PASS")

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
                "Database thay đổi trong lúc cài source; đã rollback template."
            )

        log(f, "DB_SHA_AFTER =", db_sha_after)
        log(f, "DATABASE_WRITES_THIS_RUN = 0")
        log(f, "BAI29B_SUCCESS = YES")
        log(f, "")
        log(f, "LOGIC_MOI_DUY_NHAT:")
        log(
            f,
            " - Tuổi tại 30/9 của năm học > 18; "
            "không có trường/lớp; learning_status đang trống/CHUA_XAC_DINH "
            "=> giao diện tự chọn KHONG_THUOC_DIEN.",
        )
        log(f, " - Không tự lưu DB. GV vẫn bấm Lưu theo luồng cũ.")
        log(f, " - Không ghi đè bất kỳ trạng thái học tập đã có.")
        log(
            f,
            " - Khối XMC, trình độ, MN, TH, THCS, khuyết tật, nơi học, "
            "cư trú/biến động giữ nguyên.",
        )
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
                log(f, "BAI29B_SUCCESS = NO")
                log(f, "ERROR =", repr(exc))
                if DB.exists():
                    log(f, "DB_SHA_CURRENT =", sha256_file(DB))
                log(f, "DỪNG AN TOÀN.")
                log(f, "=" * 170)
        except Exception:
            print("ERROR =", repr(exc))
        rc = 1

    raise SystemExit(rc)
