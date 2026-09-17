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
TEMPLATE = ROOT / "app" / "templates" / "surveys" / "year_records.html"
SURVEYS = ROOT / "app" / "routers" / "surveys.py"

BACKUPS = ROOT / "backups"
EXPORTS = ROOT / "exports"
OUT = EXPORTS / "SUA_GUI_FORM_NOI_HOC_KHUYET_TAT_26E.txt"

EXPECTED_DB_SHA = "cb821b5500b239756ff4b745b8f36abfaa8a44b9f43de00c26a64cd9db81ce26"

MARK_START = "<!-- === FIX26E_FORCE_FORM_FIELDS_START === -->"
MARK_END = "<!-- === FIX26E_FORCE_FORM_FIELDS_END === -->"

TARGET_IDS = (
    "study_location_scope",
    "disability_can_learn",
    "disability_access_education",
)

JS_BLOCK = '\n<!-- === FIX26E_FORCE_FORM_FIELDS_START === -->\n<script>\n(function () {\n    "use strict";\n\n    const fieldIds = [\n        "study_location_scope",\n        "disability_can_learn",\n        "disability_access_education"\n    ];\n\n    function getYearForm() {\n        return document.getElementById("year_record_form");\n    }\n\n    function bindFields() {\n        const form = getYearForm();\n        if (!form) return;\n\n        fieldIds.forEach(function (id) {\n            const field = document.getElementById(id);\n            if (!field) return;\n\n            field.setAttribute("form", "year_record_form");\n            field.disabled = false;\n            field.removeAttribute("disabled");\n            field.removeAttribute("aria-disabled");\n        });\n    }\n\n    function forceCurrentValuesIntoFormData(event) {\n        fieldIds.forEach(function (id) {\n            const field = document.getElementById(id);\n            if (!field) return;\n            event.formData.set(field.name || id, field.value || "");\n        });\n    }\n\n    document.addEventListener("DOMContentLoaded", function () {\n        const form = getYearForm();\n        if (!form) return;\n\n        bindFields();\n\n        form.addEventListener("submit", function () {\n            bindFields();\n        }, true);\n\n        form.addEventListener("formdata", forceCurrentValuesIntoFormData);\n\n        const observer = new MutationObserver(function () {\n            bindFields();\n        });\n\n        fieldIds.forEach(function (id) {\n            const field = document.getElementById(id);\n            if (!field) return;\n            observer.observe(field, {\n                attributes: true,\n                attributeFilter: ["disabled", "form", "aria-disabled"]\n            });\n        });\n    });\n})();\n</script>\n<!-- === FIX26E_FORCE_FORM_FIELDS_END === -->\n'


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def log(f, *parts):
    line = " ".join(str(x) for x in parts)
    print(line)
    f.write(line + "\n")
    f.flush()


def db_precheck():
    sha = sha256_file(DB)
    if sha != EXPECTED_DB_SHA:
        raise RuntimeError(
            "DB SHA khác nền FIX26D đã khảo sát. Dừng để không cài trên nền dữ liệu khác."
        )

    con = sqlite3.connect(
        f"file:{DB.as_posix()}?mode=ro",
        uri=True,
        timeout=30,
    )
    try:
        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
        fk = con.execute("PRAGMA foreign_key_check").fetchall()
        row = con.execute(
            """
            SELECT
                study_location_scope,
                disability_status,
                disability_can_learn,
                disability_access_education
            FROM survey_person_year_records
            WHERE survey_person_id=76
              AND school_year_id=2
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
    finally:
        con.close()

    if integrity != "ok" or fk:
        raise RuntimeError(
            f"DB health không đạt: integrity={integrity}; FK={len(fk)}"
        )

    return sha, integrity, len(fk), row


def patch_select_form_attr(text: str, select_id: str):
    pattern = re.compile(
        r'(<select\b(?=[^>]*\bid=["\']'
        + re.escape(select_id)
        + r'["\'])[^>]*)(>)',
        flags=re.I | re.S,
    )
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        raise RuntimeError(
            f"Cần đúng 1 select id={select_id}, thực tế={len(matches)}."
        )

    tag = matches[0].group(1)
    if re.search(
        r'\bform\s*=\s*["\']year_record_form["\']',
        tag,
        flags=re.I,
    ):
        return text, "FORM_ATTR_ALREADY_PRESENT"

    replacement = (
        tag
        + '\n                                        form="year_record_form"'
        + matches[0].group(2)
    )
    text = text[:matches[0].start()] + replacement + text[matches[0].end():]
    return text, "FORM_ATTR_ADDED"


def remove_old_fix26e(text: str) -> str:
    pattern = re.compile(
        re.escape(MARK_START)
        + r'.*?'
        + re.escape(MARK_END),
        flags=re.S,
    )
    return pattern.sub("", text)


def add_force_form_js(text: str) -> str:
    text = remove_old_fix26e(text)
    if "</body>" not in text:
        raise RuntimeError("year_records.html không có </body>.")
    return text.replace("</body>", JS_BLOCK + "\n</body>", 1)


def verify_backend():
    source = SURVEYS.read_text(encoding="utf-8-sig")

    required = (
        'disability_can_learn: Annotated[str, Form()]',
        'disability_access_education: Annotated[str, Form()]',
        'study_location_scope: Annotated[str | None, Form()]',
        'parsed_tri_state.get(\n        "disability_can_learn"',
        'parsed_tri_state.get(\n        "disability_access_education"',
        'record.study_location_scope = _b1512_location',
        'record.disability_can_learn = disability_can_learn_value',
        'record.disability_access_education = disability_access_education_value',
        'db.commit()',
    )
    missing = [item for item in required if item not in source]
    if missing:
        raise RuntimeError(
            "Backend hiện tại không còn đúng nền FIX26D; thiếu: "
            + repr(missing)
        )


def verify_template(text: str):
    if MARK_START not in text or MARK_END not in text:
        raise RuntimeError("Thiếu block FIX26E.")

    for select_id in TARGET_IDS:
        pattern = re.compile(
            r'<select\b(?=[^>]*\bid=["\']'
            + re.escape(select_id)
            + r'["\'])(?=[^>]*\bform=["\']year_record_form["\'])[^>]*>',
            flags=re.I | re.S,
        )
        if not pattern.search(text):
            raise RuntimeError(
                f"Select {select_id} chưa gắn form=year_record_form."
            )

    required_js = (
        'form.addEventListener("formdata", forceCurrentValuesIntoFormData)',
        'event.formData.set(field.name || id, field.value || "")',
        'field.disabled = false',
    )
    missing = [x for x in required_js if x not in text]
    if missing:
        raise RuntimeError(
            "JS FIX26E thiếu khóa gửi form: " + repr(missing)
        )


def main():
    EXPORTS.mkdir(parents=True, exist_ok=True)
    BACKUPS.mkdir(parents=True, exist_ok=True)

    with OUT.open("w", encoding="utf-8-sig", newline="\n") as f:
        log(f, "=" * 160)
        log(f, "FIX 26E - SỬA GỬI FORM NƠI HỌC + 2 CHỈ BÁO KHUYẾT TẬT")
        log(f, "NGUYÊN NHÂN: BACKEND ĐÃ LƯU ĐÚNG; CONTROL GIAO DIỆN KHÔNG ĐƯỢC GỬI ỔN ĐỊNH")
        log(f, "CHỈ SỬA TEMPLATE. KHÔNG GHI DATABASE.")
        log(f, "=" * 160)

        for p in (DB, TEMPLATE, SURVEYS):
            if not p.exists():
                raise RuntimeError(f"Không tìm thấy: {p}")

        db_sha, integrity, fk_count, test_row = db_precheck()
        log(f, "DB_SHA_BEFORE =", db_sha)
        log(f, "INTEGRITY =", integrity)
        log(f, "FK_COUNT =", fk_count)
        log(f, "TEST_RECORD_BEFORE =", test_row)

        verify_backend()
        log(f, "BACKEND_SAVE_FLOW_VERIFY = PASS")

        text_before = TEMPLATE.read_text(encoding="utf-8-sig")

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_root = BACKUPS / f"source_truoc_FIX26E_{stamp}"
        backup_file = backup_root / TEMPLATE.relative_to(ROOT)
        backup_file.parent.mkdir(parents=True, exist_ok=False)
        shutil.copy2(TEMPLATE, backup_file)
        log(f, "SOURCE_BACKUP =", backup_root)

        try:
            text_after = text_before
            statuses = {}
            for select_id in TARGET_IDS:
                text_after, status = patch_select_form_attr(
                    text_after,
                    select_id,
                )
                statuses[select_id] = status

            text_after = add_force_form_js(text_after)
            verify_template(text_after)

            TEMPLATE.write_text(text_after, encoding="utf-8")
            log(f, "PATCH_SELECTS =", statuses)
            log(f, "TEMPLATE_VERIFY = PASS")

        except Exception:
            shutil.copy2(backup_file, TEMPLATE)
            log(f, "ROLLBACK_TEMPLATE = PASS")
            raise

        db_sha_after = sha256_file(DB)
        if db_sha_after != db_sha:
            shutil.copy2(backup_file, TEMPLATE)
            raise RuntimeError(
                "DB SHA thay đổi trong lúc cài template; đã rollback template."
            )

        log(f, "DB_SHA_AFTER =", db_sha_after)
        log(f, "DATABASE_WRITES_THIS_RUN = 0")
        log(f, "FIX26E_SUCCESS = YES")
        log(f, "")
        log(f, "TEST:")
        log(f, "1. Restart Uvicorn và Ctrl+F5.")
        log(f, "2. Hồ sơ test: chọn Nơi học = Trong tỉnh hoặc Ngoài tỉnh.")
        log(f, "3. Chọn Có khả năng học tập = Có; Được tiếp cận giáo dục = Có.")
        log(f, "4. Bấm Lưu và mở lại cùng hồ sơ.")
        log(f, "5. Cả 3 lựa chọn phải giữ nguyên.")
        log(f, "6. Sau đó xuất lại MN-02.")
        log(f, "=" * 160)

    return 0


if __name__ == "__main__":
    try:
        rc = main()
    except Exception as exc:
        try:
            EXPORTS.mkdir(parents=True, exist_ok=True)
            with OUT.open("a", encoding="utf-8-sig", newline="\n") as f:
                log(f, "")
                log(f, "=" * 160)
                log(f, "FIX26E_SUCCESS = NO")
                log(f, "ERROR =", repr(exc))
                if DB.exists():
                    log(f, "DB_SHA_CURRENT =", sha256_file(DB))
                log(f, "DỪNG AN TOÀN.")
                log(f, "=" * 160)
        except Exception:
            print("ERROR =", repr(exc))
        rc = 1

    raise SystemExit(rc)
