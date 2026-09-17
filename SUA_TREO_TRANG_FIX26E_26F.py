# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(r"C:\PhoCap")
TEMPLATE = ROOT / "app" / "templates" / "surveys" / "year_records.html"
BACKUPS = ROOT / "backups"
EXPORTS = ROOT / "exports"
OUT = EXPORTS / "SUA_TREO_TRANG_FIX26E_26F.txt"

OLD_START = "<!-- === FIX26E_FORCE_FORM_FIELDS_START === -->"
OLD_END = "<!-- === FIX26E_FORCE_FORM_FIELDS_END === -->"
NEW_START = "<!-- === FIX26F_SAFE_FORM_FIELDS_START === -->"
NEW_END = "<!-- === FIX26F_SAFE_FORM_FIELDS_END === -->"

TARGET_IDS = (
    "study_location_scope",
    "disability_can_learn",
    "disability_access_education",
)

SAFE_BLOCK = '<!-- === FIX26F_SAFE_FORM_FIELDS_START === -->\n<script>\n(function () {\n    "use strict";\n    const fieldIds = [\n        "study_location_scope",\n        "disability_can_learn",\n        "disability_access_education"\n    ];\n\n    function getYearForm() {\n        return document.getElementById("year_record_form");\n    }\n\n    function prepareFieldsOnce() {\n        fieldIds.forEach(function (id) {\n            const field = document.getElementById(id);\n            if (!field) return;\n\n            if (field.getAttribute("form") !== "year_record_form") {\n                field.setAttribute("form", "year_record_form");\n            }\n            if (field.disabled) field.disabled = false;\n            if (field.hasAttribute("disabled")) field.removeAttribute("disabled");\n            if (field.hasAttribute("aria-disabled")) field.removeAttribute("aria-disabled");\n        });\n    }\n\n    function forceCurrentValuesIntoFormData(event) {\n        fieldIds.forEach(function (id) {\n            const field = document.getElementById(id);\n            if (!field) return;\n            event.formData.set(field.name || id, field.value || "");\n        });\n    }\n\n    document.addEventListener("DOMContentLoaded", function () {\n        const form = getYearForm();\n        if (!form) return;\n\n        prepareFieldsOnce();\n\n        form.addEventListener("submit", function () {\n            prepareFieldsOnce();\n        }, true);\n\n        form.addEventListener("formdata", forceCurrentValuesIntoFormData);\n    });\n})();\n</script>\n<!-- === FIX26F_SAFE_FORM_FIELDS_END === -->'


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


def remove_marked_block(text: str, start: str, end: str):
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), flags=re.S)
    matches = list(pattern.finditer(text))
    return pattern.sub("", text), len(matches)


def ensure_form_attr(text: str, select_id: str):
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

    whole = matches[0].group(0)
    if re.search(r'\bform\s*=\s*["\']year_record_form["\']', whole, flags=re.I):
        return text, "ALREADY_OK"

    replacement = (
        matches[0].group(1)
        + '\n                                        form="year_record_form"'
        + matches[0].group(2)
    )
    text = text[:matches[0].start()] + replacement + text[matches[0].end():]
    return text, "ADDED"


def verify(text: str):
    if OLD_START in text or OLD_END in text:
        raise RuntimeError("Block FIX26E cũ vẫn còn.")
    if NEW_START not in text or NEW_END not in text:
        raise RuntimeError("Thiếu block FIX26F.")

    m = re.search(re.escape(NEW_START) + r".*?" + re.escape(NEW_END), text, flags=re.S)
    if not m:
        raise RuntimeError("Không đọc được block FIX26F.")
    block = m.group(0)

    if "new MutationObserver" in block:
        raise RuntimeError("FIX26F không được chứa MutationObserver.")

    for item in (
        'form.addEventListener("formdata", forceCurrentValuesIntoFormData)',
        'event.formData.set(field.name || id, field.value || "")',
        'prepareFieldsOnce();',
    ):
        if item not in block:
            raise RuntimeError("FIX26F thiếu: " + item)

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


def main():
    if not TEMPLATE.exists():
        raise RuntimeError(f"Không tìm thấy: {TEMPLATE}")

    EXPORTS.mkdir(parents=True, exist_ok=True)
    BACKUPS.mkdir(parents=True, exist_ok=True)

    with OUT.open("w", encoding="utf-8-sig", newline="\n") as f:
        log(f, "=" * 150)
        log(f, "FIX 26F - SỬA TREO TRANG SAU FIX26E")
        log(f, "CHỈ SỬA TEMPLATE. KHÔNG GHI DATABASE.")
        log(f, "=" * 150)

        before = TEMPLATE.read_text(encoding="utf-8-sig")
        log(f, "TEMPLATE_SHA_BEFORE =", sha256_file(TEMPLATE))

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_root = BACKUPS / f"source_truoc_FIX26F_{stamp}"
        backup_file = backup_root / TEMPLATE.relative_to(ROOT)
        backup_file.parent.mkdir(parents=True, exist_ok=False)
        shutil.copy2(TEMPLATE, backup_file)
        log(f, "SOURCE_BACKUP =", backup_root)

        try:
            text, old26e = remove_marked_block(before, OLD_START, OLD_END)
            text, old26f = remove_marked_block(text, NEW_START, NEW_END)

            statuses = {}
            for select_id in TARGET_IDS:
                text, status = ensure_form_attr(text, select_id)
                statuses[select_id] = status

            if "</body>" not in text:
                raise RuntimeError("Không tìm thấy </body>.")

            text = text.replace("</body>", SAFE_BLOCK + "\n</body>", 1)
            verify(text)
            TEMPLATE.write_text(text, encoding="utf-8")
            verify(TEMPLATE.read_text(encoding="utf-8"))

            log(f, "REMOVED_FIX26E_BLOCK_COUNT =", old26e)
            log(f, "REMOVED_OLD_FIX26F_BLOCK_COUNT =", old26f)
            log(f, "SELECT_FORM_ATTR =", statuses)
            log(f, "TEMPLATE_VERIFY = PASS")
            log(f, "TEMPLATE_SHA_AFTER =", sha256_file(TEMPLATE))
            log(f, "DATABASE_WRITES_THIS_RUN = 0")
            log(f, "FIX26F_SUCCESS = YES")
            log(f, "=" * 150)

        except Exception:
            shutil.copy2(backup_file, TEMPLATE)
            log(f, "ROLLBACK_TEMPLATE = PASS")
            raise

    return 0


if __name__ == "__main__":
    try:
        rc = main()
    except Exception as exc:
        try:
            EXPORTS.mkdir(parents=True, exist_ok=True)
            with OUT.open("a", encoding="utf-8-sig", newline="\n") as f:
                log(f, "")
                log(f, "=" * 150)
                log(f, "FIX26F_SUCCESS = NO")
                log(f, "ERROR =", repr(exc))
                log(f, "DỪNG AN TOÀN.")
                log(f, "=" * 150)
        except Exception:
            print("ERROR =", repr(exc))
        rc = 1

    raise SystemExit(rc)
