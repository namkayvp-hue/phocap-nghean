from __future__ import annotations

import ast
import os
import py_compile
import re
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

PROJECT = Path(os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")).resolve()
APP = PROJECT / "app"
EXPORTS = PROJECT / "exports"
DB = PROJECT / "data" / "phocap.db"
ROUTER = APP / "routers" / "surveys.py"
TEMPLATE = APP / "templates" / "surveys" / "year_records.html"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = EXPORTS / f"backup_bai_13b_11_15_2_4_7_1a_{STAMP}"
REPORT = EXPORTS / f"bao_cao_bai_13b_11_15_2_4_7_1a_{STAMP}.txt"

PY_START = "# === BAI_13B_11_15_2_4_7_1A_FORCE_XMC_AGE15_START ==="
PY_END = "# === BAI_13B_11_15_2_4_7_1A_FORCE_XMC_AGE15_END ==="
UI_START = "<!-- === BAI_13B_11_15_2_4_7_1A_FORCE_XMC_AGE15_UI_START === -->"
UI_END = "<!-- === BAI_13B_11_15_2_4_7_1A_FORCE_XMC_AGE15_UI_END === -->"
OLD_SAVE_START = "# === BAI_13B_11_13_2_SAVE_FIELDS_START ==="
OLD_SAVE_END = "# === BAI_13B_11_13_2_SAVE_FIELDS_END ==="

FORCE_BLOCK_TEMPLATE = '# === BAI_13B_11_15_2_4_7_1A_FORCE_XMC_AGE15_START ===\n# Tuổi theo năm điều tra >= 15 => bắt buộc thuộc diện điều tra XMC.\n_b1471a_reference_year = None\n\nif school_year is not None:\n    _b1471a_year_text = str(getattr(school_year, "code", "") or "")\n    for _b1471a_token in (\n        _b1471a_year_text.replace("/", "-").replace("_", "-").split("-")\n    ):\n        _b1471a_token = _b1471a_token.strip()\n        if len(_b1471a_token) >= 4 and _b1471a_token[:4].isdigit():\n            _b1471a_reference_year = int(_b1471a_token[:4])\n            break\n\n    if (\n        _b1471a_reference_year is None\n        and getattr(school_year, "start_date", None) is not None\n    ):\n        _b1471a_reference_year = school_year.start_date.year\n\n_b1471a_age_by_year = None\n\nif (\n    _b1471a_reference_year is not None\n    and getattr(person, "date_of_birth", None) is not None\n):\n    _b1471a_age_by_year = _b1471a_reference_year - person.date_of_birth.year\n\nif _b1471a_age_by_year is not None and _b1471a_age_by_year >= 15:\n    _b131132_is_literacy_target = True\n    __RECORD_VAR__.is_literacy_target = True\n# === BAI_13B_11_15_2_4_7_1A_FORCE_XMC_AGE15_END ==='
UI_SCRIPT = '<!-- === BAI_13B_11_15_2_4_7_1A_FORCE_XMC_AGE15_UI_START === -->\n<script>\n(function () {\n    "use strict";\n\n    function parseXmcAge15() {\n        const dobText =\n            {{ (person.date_of_birth.isoformat() if person.date_of_birth else \'\') | tojson }};\n        const schoolYearText =\n            {{ (batch.school_year.code if batch.school_year else \'\') | tojson }};\n\n        if (!dobText) return null;\n\n        const birthYear = parseInt(String(dobText).slice(0, 4), 10);\n        if (!Number.isFinite(birthYear)) return null;\n\n        const matches = String(schoolYearText || "").match(/\\d{4}/g);\n        if (!matches || !matches.length) return null;\n\n        const referenceYear = parseInt(matches[0], 10);\n        if (!Number.isFinite(referenceYear)) return null;\n\n        const age = referenceYear - birthYear;\n        if (!Number.isFinite(age) || age < 0 || age > 120) return null;\n\n        return age;\n    }\n\n    function applyXmcAge15Rule() {\n        const target = document.getElementById("is_literacy_target");\n        if (!target) return;\n\n        const age = parseXmcAge15();\n        if (age === null || age < 15) return;\n\n        target.value = "CO";\n\n        Array.from(target.options || []).forEach(function (option) {\n            option.disabled = option.value !== "CO";\n        });\n\n        let note = document.getElementById("b1471a_xmc_age15_note");\n        if (!note) {\n            note = document.createElement("small");\n            note.id = "b1471a_xmc_age15_note";\n            note.style.display = "block";\n            note.style.marginTop = "6px";\n            note.style.fontWeight = "700";\n            note.style.color = "#8a4b08";\n            note.textContent =\n                "Từ 15 tuổi trở lên: bắt buộc thuộc diện điều tra Xóa mù chữ.";\n            target.insertAdjacentElement("afterend", note);\n        }\n\n        target.dispatchEvent(new Event("change", {bubbles: true}));\n    }\n\n    document.addEventListener("DOMContentLoaded", function () {\n        applyXmcAge15Rule();\n        window.setTimeout(applyXmcAge15Rule, 120);\n        window.setTimeout(applyXmcAge15Rule, 450);\n    });\n})();\n</script>\n<!-- === BAI_13B_11_15_2_4_7_1A_FORCE_XMC_AGE15_UI_END === -->'


def read_text(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(f"Không tìm thấy: {path}")
    return path.read_text(encoding="utf-8-sig", errors="strict")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def db_state() -> dict:
    if not DB.exists():
        return {"exists": False}
    conn = sqlite3.connect(str(DB))
    try:
        return {
            "exists": True,
            "integrity": str(conn.execute("PRAGMA integrity_check").fetchone()[0]),
            "fk_count": len(conn.execute("PRAGMA foreign_key_check").fetchall()),
            "record_count": int(
                conn.execute("SELECT COUNT(*) FROM survey_person_year_records").fetchone()[0]
            ),
            "target_true_count": int(
                conn.execute(
                    "SELECT COUNT(*) FROM survey_person_year_records WHERE is_literacy_target = 1"
                ).fetchone()[0]
            ),
        }
    finally:
        conn.close()


def backup_db() -> None:
    if not DB.exists():
        return
    src = sqlite3.connect(str(DB))
    dst = sqlite3.connect(str(BACKUP / DB.name))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


def restore_db() -> None:
    source = BACKUP / DB.name
    if not source.exists() or not DB.exists():
        return
    src = sqlite3.connect(str(source))
    dst = sqlite3.connect(str(DB))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


def patch_router(source: str) -> tuple[str, str]:
    ast.parse(source)

    if PY_START in source:
        return source, "Backend quy tắc 15+ đã có."

    start = source.find(OLD_SAVE_START)
    end = source.find(OLD_SAVE_END, start)

    if start < 0 or end < 0:
        raise RuntimeError("Không tìm thấy khối SAVE_FIELDS Bài 13B-11.13.2.")

    block = source[start:end]
    match = re.search(
        r"(?m)^([ \t]*)([A-Za-z_][A-Za-z0-9_]*)"
        r"\.is_literacy_target\s*=\s*_b131132_is_literacy_target\s*$",
        block,
    )
    if not match:
        raise RuntimeError(
            "Không xác định được biến record đang lưu is_literacy_target."
        )

    indent = match.group(1)
    record_var = match.group(2)
    force_block = FORCE_BLOCK_TEMPLATE.replace("__RECORD_VAR__", record_var)

    insertion = "\n" + "\n".join(
        (indent + line) if line else ""
        for line in force_block.splitlines()
    ) + "\n"

    insert_at = start + match.end()
    source = source[:insert_at] + insertion + source[insert_at:]
    ast.parse(source)

    return (
        source,
        f"Backend ép {record_var}.is_literacy_target=True khi tuổi theo năm >=15.",
    )


def patch_template(source: str) -> tuple[str, str]:
    if UI_START in source:
        return source, "UI quy tắc 15+ đã có."

    if 'id="is_literacy_target"' not in source:
        raise RuntimeError("Không tìm thấy is_literacy_target trong template.")

    pos = source.lower().rfind("</body>")
    if pos < 0:
        raise RuntimeError("Không tìm thấy </body>.")

    source = source[:pos] + "\n" + UI_SCRIPT + "\n" + source[pos:]
    return (
        source,
        "UI tự chọn Có và khóa Không/Chưa xác định cho tuổi theo năm >=15.",
    )


def parse_first_year(code, start_date) -> int | None:
    text = str(code or "")
    for token in text.replace("/", "-").replace("_", "-").split("-"):
        token = token.strip()
        if len(token) >= 4 and token[:4].isdigit():
            return int(token[:4])

    text = str(start_date or "").strip()
    if len(text) >= 4 and text[:4].isdigit():
        return int(text[:4])

    return None


def parse_birth_year(value) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None

    if len(text) >= 4 and text[:4].isdigit():
        return int(text[:4])

    found = re.findall(r"\d{4}", text)
    return int(found[-1]) if found else None


def normalize_existing_db() -> tuple[int, int]:
    if not DB.exists():
        return 0, 0

    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row

    try:
        person_cols = {
            row[1] for row in conn.execute("PRAGMA table_info(survey_people)").fetchall()
        }
        year_cols = {
            row[1] for row in conn.execute("PRAGMA table_info(school_years)").fetchall()
        }
        record_cols = {
            row[1]
            for row in conn.execute(
                "PRAGMA table_info(survey_person_year_records)"
            ).fetchall()
        }

        if not {"id", "date_of_birth"}.issubset(person_cols):
            raise RuntimeError("survey_people thiếu id/date_of_birth.")
        if not {"id", "code"}.issubset(year_cols):
            raise RuntimeError("school_years thiếu id/code.")
        if not {
            "id",
            "survey_person_id",
            "school_year_id",
            "is_literacy_target",
        }.issubset(record_cols):
            raise RuntimeError(
                "survey_person_year_records thiếu cột XMC cần thiết."
            )

        start_expr = "sy.start_date" if "start_date" in year_cols else "NULL"

        rows = conn.execute(
            f"""
            SELECT
                spr.id AS record_id,
                spr.is_literacy_target,
                sp.date_of_birth,
                sy.code AS year_code,
                {start_expr} AS start_date
            FROM survey_person_year_records AS spr
            JOIN survey_people AS sp
              ON sp.id = spr.survey_person_id
            JOIN school_years AS sy
              ON sy.id = spr.school_year_id
            """
        ).fetchall()

        eligible = 0
        ids: list[int] = []

        for row in rows:
            ref_year = parse_first_year(row["year_code"], row["start_date"])
            by = parse_birth_year(row["date_of_birth"])

            if ref_year is None or by is None:
                continue

            if ref_year - by < 15:
                continue

            eligible += 1

            if row["is_literacy_target"] != 1:
                ids.append(int(row["record_id"]))

        if ids:
            conn.executemany(
                """
                UPDATE survey_person_year_records
                SET is_literacy_target = 1
                WHERE id = ?
                """,
                [(record_id,) for record_id in ids],
            )

        conn.commit()
        return eligible, len(ids)

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def verify(router_text: str, template_text: str) -> None:
    ast.parse(router_text)

    for token in (
        PY_START,
        PY_END,
        "_b1471a_reference_year",
        "_b1471a_age_by_year",
        "_b131132_is_literacy_target = True",
        ".is_literacy_target = True",
    ):
        if token not in router_text:
            raise RuntimeError("Verifier router thiếu: " + token)

    for token in (
        UI_START,
        UI_END,
        "parseXmcAge15",
        "applyXmcAge15Rule",
        'target.value = "CO"',
        'option.value !== "CO"',
        "Từ 15 tuổi trở lên",
    ):
        if token not in template_text:
            raise RuntimeError("Verifier template thiếu: " + token)

    ui = template_text[
        template_text.find(UI_START):
        template_text.find(UI_END) + len(UI_END)
    ]

    if "MutationObserver" in ui:
        raise RuntimeError("Không cho phép MutationObserver.")


def clear_cache() -> None:
    for cache in APP.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)


def main() -> None:
    print("=" * 146)
    print(
        "BÀI 13B-11.15.2.4.7.1A - "
        "CHUẨN HÓA ĐỐI TƯỢNG ĐIỀU TRA XMC TỪ 15 TUỔI"
    )
    print("=" * 146)
    print()
    print("QUY TẮC:")
    print(" - Tuổi theo năm điều tra >=15 => Thuộc diện điều tra XMC = Có.")
    print(" - Thuộc diện điều tra KHÔNG đồng nghĩa người đó mù chữ.")
    print(" - Mức 1/mức 2 vẫn xác định riêng bằng lớp 3/lớp 5.")
    print()

    old_router = read_text(ROUTER)
    old_template = read_text(TEMPLATE)
    ast.parse(old_router)

    new_router, router_note = patch_router(old_router)
    new_template, template_note = patch_template(old_template)
    verify(new_router, new_template)

    before = db_state()

    if before.get("exists"):
        if before.get("integrity") != "ok":
            raise RuntimeError("Database integrity_check != ok trước cài.")
        if before.get("fk_count") != 0:
            raise RuntimeError("Database có lỗi foreign key trước cài.")

    EXPORTS.mkdir(parents=True, exist_ok=True)
    BACKUP.mkdir(parents=True, exist_ok=False)

    shutil.copy2(ROUTER, BACKUP / ROUTER.name)
    shutil.copy2(TEMPLATE, BACKUP / TEMPLATE.name)
    backup_db()

    try:
        if new_router != old_router:
            write_text(ROUTER, new_router)

        if new_template != old_template:
            write_text(TEMPLATE, new_template)

        eligible, changed = normalize_existing_db()

        py_compile.compile(str(ROUTER), doraise=True)
        verify(read_text(ROUTER), read_text(TEMPLATE))

        after = db_state()

        if after.get("exists"):
            if after.get("integrity") != "ok":
                raise RuntimeError("Database integrity_check != ok sau cài.")
            if after.get("fk_count") != 0:
                raise RuntimeError("Database có lỗi foreign key sau cài.")
            if after.get("record_count") != before.get("record_count"):
                raise RuntimeError("Số year-record thay đổi ngoài dự kiến.")

        clear_cache()

    except Exception:
        shutil.copy2(BACKUP / ROUTER.name, ROUTER)
        shutil.copy2(BACKUP / TEMPLATE.name, TEMPLATE)
        restore_db()
        clear_cache()
        raise

    REPORT.write_text(
        "\n".join(
            [
                "=" * 146,
                "BÀI 13B-11.15.2.4.7.1A - KẾT QUẢ",
                "=" * 146,
                "",
                "QUY TẮC:",
                " - Tuổi theo năm điều tra >=15 => is_literacy_target=True.",
                " - Đây là phạm vi điều tra, không phải kết luận mù chữ.",
                "",
                "SOURCE:",
                " - " + router_note,
                " - " + template_note,
                "",
                "DỮ LIỆU CŨ:",
                f" - Year-record >=15 hiện có: {eligible}",
                f" - Đã đổi is_literacy_target sang Có: {changed}",
                " - Không tạo record mới.",
                " - Không đổi literacy_status/completed_grade_3/completed_grade_5.",
                "",
                f"Database trước: {before}",
                f"Database sau: {after}",
                "",
                f"Backup: {BACKUP}",
            ]
        ),
        encoding="utf-8",
    )

    print("KIỂM TRA:")
    print(" - AST/py_compile router: OK")
    print(" - UI không MutationObserver: OK")
    print(" - integrity_check: OK")
    print(" - foreign_key_check: 0")
    print(" - Không tạo/xóa year-record: OK")
    print()
    print("Year-record >=15 hiện có:", eligible)
    print("Đã chuẩn hóa sang Thuộc diện XMC = Có:", changed)
    print()
    print("Backup:", BACKUP)
    print("Báo cáo:", REPORT)
    print()
    print("=" * 146)
    print("BÀI 13B-11.15.2.4.7.1A THÀNH CÔNG")
    print("=" * 146)


if __name__ == "__main__":
    main()
