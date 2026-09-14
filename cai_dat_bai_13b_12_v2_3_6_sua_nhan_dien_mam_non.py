# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
import py_compile
import re
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from jinja2 import Environment

PROJECT = Path(r"C:\PhoCap")
APP = PROJECT / "app"
DB = PROJECT / "data" / "phocap.db"
EXPORTS = PROJECT / "exports"

SURVEYS = APP / "routers" / "surveys.py"
YEAR_TEMPLATE = APP / "templates" / "surveys" / "year_records.html"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = EXPORTS / f"backup_bai_13b_12_v2_3_6_{STAMP}"
DB_BACKUP = BACKUP / "phocap.db"
REPORT = EXPORTS / f"bao_cao_cai_bai_13b_12_v2_3_6_{STAMP}.txt"

PARSER_MARKER = "# === BAI_13B_12_V2_3_1_GRADE_PARSER_START ==="
V236_GUARD_MARKER = "# === BAI_13B_12_V2_3_6_PRESCHOOL_GRADE_GUARD_START ==="
V236_UI_MARKER = "BAI_13B_12_V2_3_6_AUTHORITATIVE_LEVEL_UI_START"

OLD_PARSER_IF = '    if (\n        "tuổi" not in _b13231_class_fold\n        and "tuoi" not in _b13231_class_fold\n    ):\n'
NEW_PARSER_IF = '    if (\n        "tuổi" not in _b13231_class_fold\n        and "tuoi" not in _b13231_class_fold\n        and not _b13236_is_preschool\n    ):\n'
PRESCHOOL_GUARD = '\n    # === BAI_13B_12_V2_3_6_PRESCHOOL_GRADE_GUARD_START ===\n    _b13236_school_text = " ".join(\n        [\n            str(\n                getattr(selected_school, "name", "")\n                if selected_school is not None\n                else ""\n            ),\n            str(school_name_reported or ""),\n        ]\n    ).casefold()\n\n    _b13236_is_preschool = any(\n        token in _b13236_school_text\n        for token in (\n            "mầm non",\n            "mam non",\n            "mẫu giáo",\n            "mau giao",\n            "nhà trẻ",\n            "nha tre",\n        )\n    ) or bool(\n        re.search(\n            r"(^|\\s)mn(\\s|$)",\n            _b13236_school_text,\n            flags=re.IGNORECASE,\n        )\n    )\n    # === BAI_13B_12_V2_3_6_PRESCHOOL_GRADE_GUARD_END ===\n\n'
AUTHORITATIVE_UI = '\n<!-- === BAI_13B_12_V2_3_6_AUTHORITATIVE_LEVEL_UI_START === -->\n<script>\n(function () {\n    "use strict";\n\n    function textOf(selector) {\n        const el = document.querySelector(selector);\n        if (!el) return "";\n\n        if (el.tagName === "SELECT") {\n            const option = el.options[el.selectedIndex];\n            return String(\n                option ? (option.textContent || option.value || "") : ""\n            ).trim();\n        }\n\n        return String(el.value || el.textContent || "").trim();\n    }\n\n    function normalize(value) {\n        return String(value || "")\n            .normalize("NFD")\n            .replace(/[\\u0300-\\u036f]/g, "")\n            .toLowerCase()\n            .replace(/\\s+/g, " ")\n            .trim();\n    }\n\n    function schoolText() {\n        return normalize(\n            [\n                textOf("#school_search"),\n                textOf("#school_selected"),\n                textOf(\'[name="school_id"]\'),\n                textOf(\'[name="school_name_reported"]\')\n            ].join(" ")\n        );\n    }\n\n    function classText() {\n        return normalize(\n            [\n                textOf("#class_search"),\n                textOf("#class_selected"),\n                textOf(\'[name="class_id"]\'),\n                textOf(\'[name="class_name_reported"]\')\n            ].join(" ")\n        );\n    }\n\n    function currentYearStart() {\n        const yearSelect =\n            document.getElementById("year_filter")\n            || document.querySelector(\'select[name="school_year_id"]\');\n\n        if (!yearSelect) return null;\n\n        const option = yearSelect.options[yearSelect.selectedIndex];\n        const raw = String(\n            option ? (option.textContent || option.value || "") : ""\n        );\n        const match = raw.match(/20\\d{2}/);\n        return match ? Number(match[0]) : null;\n    }\n\n    function birthYear() {\n        const raw =\n            {{ (person.date_of_birth.isoformat() if person.date_of_birth else \'\') | tojson }};\n        const match = String(raw || "").match(/^(19|20)\\d{2}/);\n        return match ? Number(match[0]) : null;\n    }\n\n    function ageInSchoolYear() {\n        const year = currentYearStart();\n        const birth = birthYear();\n\n        if (!Number.isFinite(year) || !Number.isFinite(birth)) {\n            return null;\n        }\n\n        const age = year - birth;\n        return age >= 0 && age <= 120 ? age : null;\n    }\n\n    function detectLevelAuthoritatively() {\n        const school = schoolText();\n        const klass = classText();\n        const age = ageInSchoolYear();\n\n        if (\n            school.includes("mam non")\n            || school.includes("mau giao")\n            || school.includes("nha tre")\n            || /(^|\\s)mn(\\s|$)/.test(school)\n        ) {\n            return "MN";\n        }\n\n        if (\n            school.includes("thcs")\n            || school.includes("trung hoc co so")\n        ) {\n            return "THCS";\n        }\n\n        if (\n            school.includes("tieu hoc")\n            || /(^|\\s)th(\\s|$)/.test(school)\n        ) {\n            return "TH";\n        }\n\n        if (Number.isFinite(age) && age <= 5) {\n            return "MN";\n        }\n\n        const explicitGrade = klass.match(\n            /(?:lop|khoi)\\s*(1[0-2]|[1-9])\\b/\n        );\n        const shortGrade = klass.match(\n            /^\\s*(1[0-2]|[1-9])(?:\\s*[a-z]\\d*)?\\s*$/\n        );\n        const gradeMatch = explicitGrade || shortGrade;\n\n        if (gradeMatch) {\n            const grade = Number(gradeMatch[1]);\n            if (grade >= 1 && grade <= 5) return "TH";\n            if (grade >= 6 && grade <= 9) return "THCS";\n        }\n\n        return "";\n    }\n\n    function hardVisible(element, visible) {\n        if (!element) return;\n\n        element.hidden = !visible;\n\n        if (visible) {\n            element.removeAttribute("hidden");\n            element.style.removeProperty("display");\n            element.style.display = "";\n        } else {\n            element.setAttribute("hidden", "");\n            element.style.display = "none";\n        }\n    }\n\n    function applyAuthoritativeLevel() {\n        const level = detectLevelAuthoritatively();\n\n        hardVisible(\n            document.getElementById("b131133_preschool_indicators"),\n            level === "MN"\n        );\n        hardVisible(\n            document.getElementById("b131132_primary_indicators"),\n            level === "TH"\n        );\n        hardVisible(\n            document.getElementById("b131132_thcs_indicators"),\n            level === "THCS"\n        );\n\n        document.body.dataset.b13236Level = level || "OTHER";\n    }\n\n    function bind(selector) {\n        const element = document.querySelector(selector);\n        if (!element) return;\n\n        ["change", "input"].forEach(function (eventName) {\n            element.addEventListener(eventName, function () {\n                window.setTimeout(applyAuthoritativeLevel, 0);\n                window.setTimeout(applyAuthoritativeLevel, 120);\n            });\n        });\n    }\n\n    document.addEventListener("DOMContentLoaded", function () {\n        [\n            "#year_filter",\n            \'select[name="school_year_id"]\',\n            "#school_search",\n            "#school_selected",\n            \'[name="school_id"]\',\n            \'[name="school_name_reported"]\',\n            "#class_search",\n            "#class_selected",\n            \'[name="class_id"]\',\n            \'[name="class_name_reported"]\'\n        ].forEach(bind);\n\n        applyAuthoritativeLevel();\n\n        [80, 250, 700, 1500].forEach(function (delay) {\n            window.setTimeout(applyAuthoritativeLevel, delay);\n        });\n    });\n})();\n</script>\n<!-- === BAI_13B_12_V2_3_6_AUTHORITATIVE_LEVEL_UI_END === -->\n'


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def write_text(path: Path, value: str) -> None:
    path.write_text(value, encoding="utf-8")


def backup_file(path: Path) -> None:
    target = BACKUP / path.relative_to(PROJECT)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, target)


def restore_file(path: Path) -> None:
    source = BACKUP / path.relative_to(PROJECT)
    if source.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, path)


def backup_db() -> None:
    src = sqlite3.connect(str(DB))
    dst = sqlite3.connect(str(DB_BACKUP))
    try:
        src.backup(dst)
        dst.commit()
    finally:
        dst.close()
        src.close()


def restore_db() -> None:
    if not DB_BACKUP.exists():
        return
    src = sqlite3.connect(str(DB_BACKUP))
    dst = sqlite3.connect(str(DB))
    try:
        src.backup(dst)
        dst.commit()
    finally:
        dst.close()
        src.close()


def db_state() -> dict:
    con = sqlite3.connect(str(DB))
    try:
        return {
            "integrity": str(
                con.execute("PRAGMA integrity_check").fetchone()[0]
            ),
            "fk_count": len(
                con.execute("PRAGMA foreign_key_check").fetchall()
            ),
            "people": int(
                con.execute("SELECT COUNT(*) FROM survey_people").fetchone()[0]
            ),
            "year_records": int(
                con.execute(
                    "SELECT COUNT(*) FROM survey_person_year_records"
                ).fetchone()[0]
            ),
        }
    finally:
        con.close()


def patch_surveys(source: str) -> str:
    if V236_GUARD_MARKER in source:
        return source

    marker_pos = source.find(PARSER_MARKER)
    if marker_pos < 0:
        raise RuntimeError("Không tìm thấy parser V2.3.1.")

    source = (
        source[:marker_pos]
        + PRESCHOOL_GUARD
        + source[marker_pos:]
    )

    parser_pos = source.find(PARSER_MARKER)
    window = source[parser_pos:parser_pos + 5000]

    if OLD_PARSER_IF not in window:
        raise RuntimeError(
            "Không tìm thấy điều kiện parser V2.3.1 đúng bản dự kiến."
        )

    fixed_window = window.replace(
        OLD_PARSER_IF,
        NEW_PARSER_IF,
        1,
    )

    return (
        source[:parser_pos]
        + fixed_window
        + source[parser_pos + len(window):]
    )


def patch_template(source: str) -> str:
    if V236_UI_MARKER in source:
        return source

    if 'id="b131133_preschool_indicators"' not in source:
        raise RuntimeError("Không tìm thấy khối chỉ báo PCGDMN.")

    pos = source.rfind("</body>")
    if pos < 0:
        raise RuntimeError("year_records.html thiếu </body>.")

    return source[:pos] + AUTHORITATIVE_UI + source[pos:]


def normalize_wrong_preschool_grade() -> dict:
    con = sqlite3.connect(str(DB))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")

    result = {
        "checked": 0,
        "preschool_detected": 0,
        "wrong_grade_corrected": 0,
    }

    try:
        rows = con.execute(
            """
            SELECT
                spr.id,
                spr.learning_status,
                spr.school_name_reported,
                spr.highest_completed_grade,
                sp.date_of_birth,
                sy.code AS school_year_code,
                sy.start_date AS school_year_start,
                s.name AS school_name
            FROM survey_person_year_records spr
            JOIN survey_people sp
              ON sp.id = spr.survey_person_id
            JOIN school_years sy
              ON sy.id = spr.school_year_id
            LEFT JOIN schools s
              ON s.id = spr.school_id
            ORDER BY spr.id
            """
        ).fetchall()

        for row in rows:
            result["checked"] += 1

            if str(row["learning_status"] or "").strip().upper() != "DANG_HOC":
                continue

            school_text = " ".join(
                [
                    str(row["school_name"] or ""),
                    str(row["school_name_reported"] or ""),
                ]
            ).casefold()

            by_school = (
                any(
                    token in school_text
                    for token in (
                        "mầm non",
                        "mam non",
                        "mẫu giáo",
                        "mau giao",
                        "nhà trẻ",
                        "nha tre",
                    )
                )
                or re.search(
                    r"(^|\s)mn(\s|$)",
                    school_text,
                    flags=re.IGNORECASE,
                )
                is not None
            )

            ref_match = re.search(
                r"(20\d{2})",
                str(
                    row["school_year_code"]
                    or row["school_year_start"]
                    or ""
                ),
            )
            birth_match = re.match(
                r"(19|20)\d{2}",
                str(row["date_of_birth"] or ""),
            )

            age = None
            if ref_match and birth_match:
                age = int(ref_match.group(1)) - int(birth_match.group(0))

            by_age = age is not None and 0 <= age <= 5

            if not (by_school or by_age):
                continue

            result["preschool_detected"] += 1

            current_highest = row["highest_completed_grade"]

            if current_highest is not None and int(current_highest) > 0:
                con.execute(
                    """
                    UPDATE survey_person_year_records
                    SET
                        highest_completed_grade = 0,
                        education_attainment_level =
                            'CHUA_HOAN_THANH_TIEU_HOC',
                        completed_grade_3 = NULL,
                        completed_grade_5 = NULL,
                        completed_primary_program = NULL,
                        completed_lower_secondary_program = NULL
                    WHERE id = ?
                    """,
                    (int(row["id"]),),
                )
                result["wrong_grade_corrected"] += 1

        con.commit()
        return result

    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def verify_source() -> None:
    surveys = read_text(SURVEYS)
    template = read_text(YEAR_TEMPLATE)

    if V236_GUARD_MARKER not in surveys:
        raise RuntimeError("Thiếu guard Mầm non V2.3.6.")
    if "and not _b13236_is_preschool" not in surveys:
        raise RuntimeError("Parser vẫn chưa chặn lớp 5A Mầm non.")
    if V236_UI_MARKER not in template:
        raise RuntimeError("Thiếu UI phân cấp V2.3.6.")
    if 'id="b131133_preschool_indicators"' not in template:
        raise RuntimeError("Thiếu khối PCGDMN.")

    ast.parse(surveys)
    py_compile.compile(str(SURVEYS), doraise=True)
    Environment().parse(template)


def main() -> int:
    print("=" * 120)
    print(
        "BÀI 13B-12 V2.3.6 - "
        "SỬA NHẬN DIỆN MẦM NON / LỚP 5A"
    )
    print("=" * 120)

    for path in (DB, SURVEYS, YEAR_TEMPLATE):
        if not path.exists():
            print("DỪNG AN TOÀN: thiếu", path)
            return 2

    before = db_state()
    print("integrity_check:", before["integrity"])
    print("foreign_key_check:", before["fk_count"], "lỗi")

    if before["integrity"].lower() != "ok" or before["fk_count"] != 0:
        print("DỪNG: database chưa đạt kiểm tra.")
        return 3

    surveys = read_text(SURVEYS)
    template = read_text(YEAR_TEMPLATE)

    for token in (
        "BAI_13B_12_V2_3_1_GRADE_PARSER_START",
        "BAI_13B_12_V2_3_3_XMC_SELECTED_YEAR_UI_START",
        "BAI_13B_12_V2_3_4_ALWAYS_SHOW_CURRENT_SCHOOL_CLASS",
    ):
        if token not in surveys and token not in template:
            print("DỪNG AN TOÀN: thiếu nền", token)
            return 4

    if V236_GUARD_MARKER in surveys and V236_UI_MARKER in template:
        print("V2.3.6 đã cài. Không cài lặp.")
        return 0

    try:
        new_surveys = patch_surveys(surveys)
        new_template = patch_template(template)

        ast.parse(new_surveys)
        Environment().parse(new_template)

    except Exception as exc:
        print("DỪNG AN TOÀN TRƯỚC KHI GHI FILE:")
        print(type(exc).__name__ + ":", exc)
        return 5

    EXPORTS.mkdir(parents=True, exist_ok=True)
    BACKUP.mkdir(parents=True, exist_ok=False)

    backup_file(SURVEYS)
    backup_file(YEAR_TEMPLATE)
    backup_db()

    print("Backup:", BACKUP)

    try:
        write_text(SURVEYS, new_surveys)
        write_text(YEAR_TEMPLATE, new_template)

        verify_source()

        normalized = normalize_wrong_preschool_grade()
        after = db_state()

        if after["integrity"].lower() != "ok":
            raise RuntimeError("integrity_check không đạt sau cài.")
        if after["fk_count"] != 0:
            raise RuntimeError("foreign_key_check có lỗi sau cài.")
        if after["people"] != before["people"]:
            raise RuntimeError("Số nhân khẩu thay đổi ngoài dự kiến.")
        if after["year_records"] != before["year_records"]:
            raise RuntimeError("Số year-record thay đổi ngoài dự kiến.")

        for cache in APP.rglob("__pycache__"):
            if cache.is_dir():
                shutil.rmtree(cache, ignore_errors=True)

    except Exception as exc:
        print()
        print("CÓ LỖI - ĐANG ROLLBACK...")
        print(type(exc).__name__ + ":", exc)

        restore_file(SURVEYS)
        restore_file(YEAR_TEMPLATE)
        restore_db()

        print("ĐÃ KHÔI PHỤC.")
        return 9

    REPORT.write_text(
        "\n".join(
            [
                "=" * 120,
                "BÁO CÁO CÀI BÀI 13B-12 V2.3.6",
                "=" * 120,
                f"Thời gian: {datetime.now():%d/%m/%Y %H:%M:%S}",
                "",
                "NGUYÊN NHÂN:",
                "- Tên lớp Mầm non có thể là 3A/4A/5A.",
                "- Parser cũ coi 5A là lớp 5 Tiểu học.",
                "- Vì vậy chỉ báo PCGDMN bị ẩn và trình độ bị suy luận sai.",
                "",
                "ĐÃ SỬA:",
                "- Ưu tiên cấp trường trước tên lớp.",
                "- Tuổi <=5 là lớp bảo vệ khi cấp trường chưa rõ.",
                "- Không tự điền chỉ báo MN; giáo viên nhập thực tế.",
                "",
                "CHUẨN HÓA:",
                repr(normalized),
                "",
                f"integrity_check: {after['integrity']}",
                f"foreign_key_check: {after['fk_count']} lỗi",
                f"Backup: {BACKUP}",
            ]
        )
        + "\n",
        encoding="utf-8-sig",
    )

    print()
    print("=" * 120)
    print("CÀI ĐẶT THÀNH CÔNG BÀI 13B-12 V2.3.6")
    print("=" * 120)
    print("Chuẩn hóa:", normalized)
    print("Báo cáo:", REPORT)
    print("Backup:", BACKUP)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
