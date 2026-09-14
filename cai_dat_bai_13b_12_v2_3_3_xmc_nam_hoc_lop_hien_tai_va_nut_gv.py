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

ACCESS = APP / "access_control.py"
SURVEYS = APP / "routers" / "surveys.py"
YEAR_TEMPLATE = APP / "templates" / "surveys" / "year_records.html"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = EXPORTS / f"backup_bai_13b_12_v2_3_3_{STAMP}"
DB_BACKUP = BACKUP / "phocap.db"
REPORT = EXPORTS / f"bao_cao_cai_bai_13b_12_v2_3_3_{STAMP}.txt"

OLD_ACCESS_SCOPE = '        # === BAI_13B_12_V2_2_ACCESS_SCOPE_START ===\n        if normalized_path.startswith(\n            "/dieu-tra/phan-cong-to-dieu-tra/nhap-ho-moi/"\n        ):\n            if role_code != TEACHER_ROLE_CODE:\n                return False\n            user_id = auth_user.get("id")\n            if user_id is None:\n                return False\n            allowed = db.execute(\n                text(\n                    """\n                    SELECT 1\n                    FROM survey_investigation_teams AS t\n                    JOIN survey_investigation_team_members AS tm\n                      ON tm.team_id = t.id\n                    WHERE t.survey_batch_id = :batch_id\n                      AND t.status = \'SENT\'\n                      AND tm.user_id = :user_id\n                    LIMIT 1\n                    """\n                ),\n                {\n                    "batch_id": int(batch_id),\n                    "user_id": int(user_id),\n                },\n            ).scalar()\n            return allowed is not None\n        # === BAI_13B_12_V2_2_ACCESS_SCOPE_END ===\n'
NEW_ACCESS_SCOPE = '        # === BAI_13B_12_V2_2_ACCESS_SCOPE_START ===\n        if normalized_path.startswith(\n            "/dieu-tra/phan-cong-to-dieu-tra/nhap-ho-moi/"\n        ):\n            if role_code != TEACHER_ROLE_CODE:\n                return False\n\n            user_id = auth_user.get("id")\n            if user_id is None:\n                return False\n\n            # === BAI_13B_12_V2_3_2_EXTRACT_BATCH_ID_START ===\n            # Route này có dạng:\n            # /dieu-tra/phan-cong-to-dieu-tra/nhap-ho-moi/<batch_id>\n            # /.../<batch_id>/quyen\n            # /.../<batch_id>/them\n            # Không dùng biến batch_id của các nhánh phía dưới vì tại đây\n            # biến đó chưa được gán, gây UnboundLocalError.\n            _b13232_prefix = (\n                "/dieu-tra/phan-cong-to-dieu-tra/nhap-ho-moi/"\n            )\n            _b13232_tail = normalized_path[\n                len(_b13232_prefix):\n            ]\n            _b13232_batch_token = (\n                _b13232_tail.split("/", 1)[0].strip()\n            )\n            try:\n                _b13232_batch_id = int(\n                    _b13232_batch_token\n                )\n            except (TypeError, ValueError):\n                return False\n\n            if _b13232_batch_id <= 0:\n                return False\n            # === BAI_13B_12_V2_3_2_EXTRACT_BATCH_ID_END ===\n\n            allowed = db.execute(\n                text(\n                    """\n                    SELECT 1\n                    FROM survey_investigation_teams AS t\n                    JOIN survey_investigation_team_members AS tm\n                      ON tm.team_id = t.id\n                    WHERE t.survey_batch_id = :batch_id\n                      AND t.status = \'SENT\'\n                      AND tm.user_id = :user_id\n                    LIMIT 1\n                    """\n                ),\n                {\n                    "batch_id": _b13232_batch_id,\n                    "user_id": int(user_id),\n                },\n            ).scalar()\n            return allowed is not None\n        # === BAI_13B_12_V2_2_ACCESS_SCOPE_END ===\n'
INFERENCE_OLD = '        if _b1312v21_grade_value is None:\n            _b1312v21_grade_value = (\n                _b1323_inferred_completed\n            )\n\n        if _b1312v21_level_value == "CHUA_XAC_DINH":\n            if _b1323_current_grade >= 10:\n                # Đang học THPT => đã hoàn thành THCS.\n                _b1312v21_level_value = "THCS"\n            elif _b1323_current_grade >= 6:\n                # Đang học THCS => đã hoàn thành Tiểu học.\n                _b1312v21_level_value = "TIEU_HOC"\n            elif _b1323_current_grade >= 1:\n                _b1312v21_level_value = (\n                    "CHUA_HOAN_THANH_TIEU_HOC"\n                )\n'
INFERENCE_NEW = '        # === BAI_13B_12_V2_3_3_CURRENT_CLASS_SOURCE_START ===\n        _b1312v21_grade_value = (\n            _b1323_inferred_completed\n        )\n\n        if _b1323_current_grade >= 10:\n            _b1312v21_level_value = "THCS"\n        elif _b1323_current_grade >= 6:\n            _b1312v21_level_value = "TIEU_HOC"\n        elif _b1323_current_grade >= 1:\n            _b1312v21_level_value = (\n                "CHUA_HOAN_THANH_TIEU_HOC"\n            )\n        # === BAI_13B_12_V2_3_3_CURRENT_CLASS_SOURCE_END ===\n'
XMC_UI = '\n<!-- === BAI_13B_12_V2_3_3_XMC_SELECTED_YEAR_UI_START === -->\n<script>\n(function () {\n    "use strict";\n\n    function yearText() {\n        const select =\n            document.getElementById("year_filter")\n            || document.querySelector(\n                \'select[name="school_year_id"]\'\n            );\n        if (!select) return "";\n        const option =\n            select.options[select.selectedIndex];\n        return option\n            ? String(\n                option.textContent\n                || option.value\n                || ""\n            ).trim()\n            : "";\n    }\n\n    function applyRule() {\n        const target =\n            document.getElementById(\n                "is_literacy_target"\n            );\n        if (!target) return;\n\n        const yearMatch =\n            yearText().match(/20\\d{2}/);\n        const dobText =\n            {{ (person.date_of_birth.isoformat() if person.date_of_birth else \'\') | tojson }};\n        const birthMatch =\n            String(dobText || "").match(\n                /^(19|20)\\d{2}/\n            );\n\n        if (!yearMatch || !birthMatch) {\n            return;\n        }\n\n        const age =\n            Number(yearMatch[0])\n            - Number(birthMatch[0]);\n\n        if (\n            !Number.isFinite(age)\n            || age < 0\n            || age > 120\n        ) {\n            return;\n        }\n\n        const desired =\n            age >= 15 ? "CO" : "KHONG";\n\n        target.value = desired;\n\n        Array.from(\n            target.options || []\n        ).forEach(function (option) {\n            option.disabled =\n                option.value !== desired;\n        });\n\n        const label =\n            document.querySelector(\n                \'label[for="is_literacy_target"]\'\n            );\n        if (label) {\n            label.textContent =\n                "Thuộc phạm vi điều tra "\n                + "Xóa mù chữ – "\n                + yearText();\n        }\n\n        let note =\n            document.getElementById(\n                "b13233_xmc_year_note"\n            );\n        if (!note) {\n            note =\n                document.createElement("small");\n            note.id =\n                "b13233_xmc_year_note";\n            note.style.display = "block";\n            note.style.marginTop = "6px";\n            note.style.fontWeight = "700";\n            note.style.color = "#8a4b08";\n            target.insertAdjacentElement(\n                "afterend",\n                note\n            );\n        }\n\n        note.textContent =\n            "Năm học đang xét: "\n            + yearText()\n            + " · tuổi: "\n            + age\n            + (\n                age >= 15\n                ? " · thuộc phạm vi XMC; "\n                  + "mức biết chữ xác định riêng "\n                  + "từ trình độ/lớp đã hoàn thành."\n                : " · chưa thuộc phạm vi XMC."\n            );\n\n        target.dispatchEvent(\n            new Event(\n                "change",\n                {bubbles: true}\n            )\n        );\n    }\n\n    document.addEventListener(\n        "DOMContentLoaded",\n        function () {\n            const select =\n                document.getElementById(\n                    "year_filter"\n                )\n                || document.querySelector(\n                    \'select[name="school_year_id"]\'\n                );\n\n            if (select) {\n                select.addEventListener(\n                    "change",\n                    applyRule\n                );\n            }\n\n            applyRule();\n            window.setTimeout(\n                applyRule,\n                150\n            );\n            window.setTimeout(\n                applyRule,\n                500\n            );\n        }\n    );\n})();\n</script>\n<!-- === BAI_13B_12_V2_3_3_XMC_SELECTED_YEAR_UI_END === -->\n'


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def write_text(path: Path, text_value: str) -> None:
    path.write_text(text_value, encoding="utf-8")


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


def state() -> dict:
    con = sqlite3.connect(str(DB))
    try:
        return {
            "integrity": str(
                con.execute(
                    "PRAGMA integrity_check"
                ).fetchone()[0]
            ),
            "fk": len(
                con.execute(
                    "PRAGMA foreign_key_check"
                ).fetchall()
            ),
            "records": int(
                con.execute(
                    "SELECT COUNT(*) "
                    "FROM survey_person_year_records"
                ).fetchone()[0]
            ),
            "people": int(
                con.execute(
                    "SELECT COUNT(*) "
                    "FROM survey_people"
                ).fetchone()[0]
            ),
        }
    finally:
        con.close()


def patch_access(source: str) -> str:
    if (
        "BAI_13B_12_V2_3_2_"
        "EXTRACT_BATCH_ID_START"
        in source
    ):
        return source

    if OLD_ACCESS_SCOPE not in source:
        raise RuntimeError(
            "Không tìm thấy block quyền V2.2 "
            "để tích hợp sửa lỗi V2.3.2."
        )

    return source.replace(
        OLD_ACCESS_SCOPE,
        NEW_ACCESS_SCOPE,
        1,
    )


def patch_surveys(source: str) -> str:
    if (
        "BAI_13B_12_V2_3_3_"
        "CURRENT_CLASS_SOURCE_START"
        not in source
    ):
        if INFERENCE_OLD not in source:
            raise RuntimeError(
                "Không tìm thấy block suy luận "
                "trình độ V2.3.1."
            )
        source = source.replace(
            INFERENCE_OLD,
            INFERENCE_NEW,
            1,
        )

    if (
        "BAI_13B_12_V2_3_3_"
        "XMC_BIDIRECTIONAL"
        in source
    ):
        return source

    start_marker = (
        "# === BAI_13B_11_15_2_4_7_1A_"
        "FORCE_XMC_AGE15_START ==="
    )
    end_marker = (
        "# === BAI_13B_11_15_2_4_7_1A_"
        "FORCE_XMC_AGE15_END ==="
    )

    cursor = 0
    pieces = []
    count = 0

    while True:
        start = source.find(
            start_marker,
            cursor,
        )
        if start < 0:
            pieces.append(
                source[cursor:]
            )
            break

        end = source.find(
            end_marker,
            start,
        )
        if end < 0:
            raise RuntimeError(
                "Block XMC AGE15 không khép kín."
            )
        end += len(end_marker)

        pieces.append(
            source[cursor:start]
        )
        block = source[start:end]

        old_condition = (
            "if _b1471a_age_by_year "
            "is not None and "
            "_b1471a_age_by_year >= 15:"
        )
        if old_condition not in block:
            raise RuntimeError(
                "Block XMC AGE15 "
                "khác bản dự kiến."
            )

        match = re.search(
            r"([A-Za-z_][A-Za-z0-9_]*)"
            r"\.is_literacy_target = True",
            block,
        )
        if not match:
            raise RuntimeError(
                "Không xác định được biến "
                "year-record trong block XMC."
            )

        record_var = match.group(1)

        block = block.replace(
            start_marker,
            start_marker
            + "\n"
            + "# === BAI_13B_12_V2_3_3_"
            "XMC_BIDIRECTIONAL ===",
            1,
        )
        block = block.replace(
            old_condition,
            "if _b1471a_age_by_year "
            "is not None:",
            1,
        )
        block = block.replace(
            "_b131132_is_literacy_target = True",
            "_b131132_is_literacy_target = "
            "(_b1471a_age_by_year >= 15)",
            1,
        )
        block = block.replace(
            f"{record_var}.is_literacy_target = True",
            f"{record_var}.is_literacy_target = "
            "_b131132_is_literacy_target",
            1,
        )

        pieces.append(block)
        cursor = end
        count += 1

    if count < 1:
        raise RuntimeError(
            "Không tìm thấy block XMC AGE15."
        )

    return "".join(pieces)


def patch_template(source: str) -> str:
    source = source.replace(
        "Thuộc phạm vi điều tra "
        "Xóa mù chữ (theo tuổi)",
        "Thuộc phạm vi điều tra "
        "Xóa mù chữ trong năm học đang xét",
    )

    if (
        "BAI_13B_12_V2_3_3_"
        "XMC_SELECTED_YEAR_UI_START"
        not in source
    ):
        pos = source.rfind(
            "</body>"
        )
        if pos < 0:
            raise RuntimeError(
                "year_records.html thiếu </body>."
            )
        source = (
            source[:pos]
            + XMC_UI
            + source[pos:]
        )

    return source


def norm(value) -> str:
    return " ".join(
        str(value or "")
        .strip()
        .casefold()
        .split()
    )


def parse_grade(value) -> int | None:
    raw = str(
        value or ""
    ).strip()
    folded = raw.casefold()

    if (
        "tuổi" in folded
        or "tuoi" in folded
    ):
        return None

    match = re.search(
        r"(?i)\b(?:lớp|lop|khối|khoi)"
        r"\s*(1[0-2]|[1-9])\b",
        raw,
    )
    if match is None:
        match = re.match(
            r"^\s*(1[0-2]|[1-9])"
            r"(?:\s*[A-Za-z]\d*)?\s*$",
            raw,
        )

    return (
        int(match.group(1))
        if match
        else None
    )


def first_year(value) -> int | None:
    match = re.search(
        r"(20\d{2})",
        str(value or ""),
    )
    return (
        int(match.group(1))
        if match
        else None
    )


def birth_year(value) -> int | None:
    match = re.match(
        r"(19|20)\d{2}",
        str(value or ""),
    )
    return (
        int(match.group(0))
        if match
        else None
    )


def normalize_db() -> dict:
    con = sqlite3.connect(str(DB))
    con.row_factory = sqlite3.Row
    con.execute(
        "PRAGMA foreign_keys=ON"
    )

    result = {
        "school_linked": 0,
        "class_linked": 0,
        "grade_corrected": 0,
        "attainment_corrected": 0,
        "xmc_to_yes": 0,
        "xmc_to_no": 0,
        "updated": 0,
    }

    try:
        schools = con.execute(
            """
            SELECT id, name
            FROM schools
            WHERE is_active = 1
            ORDER BY id
            """
        ).fetchall()

        rows = con.execute(
            """
            SELECT
                spr.id,
                spr.school_year_id,
                spr.school_id,
                spr.class_id,
                spr.school_name_reported,
                spr.class_name_reported,
                spr.learning_status,
                spr.highest_completed_grade,
                spr.education_attainment_level,
                spr.is_literacy_target,
                spr.completed_grade_3,
                spr.completed_grade_5,
                spr.literacy_status,
                sp.date_of_birth,
                sy.code AS year_code,
                sy.start_date AS year_start,
                c.name AS class_name
            FROM survey_person_year_records spr
            JOIN survey_people sp
              ON sp.id = spr.survey_person_id
            JOIN school_years sy
              ON sy.id = spr.school_year_id
            LEFT JOIN classes c
              ON c.id = spr.class_id
            ORDER BY spr.id
            """
        ).fetchall()

        for row in rows:
            school_id = row["school_id"]
            class_id = row["class_id"]
            class_name = row["class_name"]
            highest = row[
                "highest_completed_grade"
            ]
            level = str(
                row[
                    "education_attainment_level"
                ]
                or "CHUA_XAC_DINH"
            ).strip().upper()
            target = row[
                "is_literacy_target"
            ]
            g3 = row["completed_grade_3"]
            g5 = row["completed_grade_5"]
            literacy = str(
                row["literacy_status"]
                or "CHUA_XAC_DINH"
            ).strip().upper()

            changed = False

            if (
                school_id is None
                and row[
                    "school_name_reported"
                ]
            ):
                wanted = norm(
                    row[
                        "school_name_reported"
                    ]
                )
                matches = [
                    int(item["id"])
                    for item in schools
                    if norm(item["name"])
                    == wanted
                ]
                if len(matches) == 1:
                    school_id = matches[0]
                    result[
                        "school_linked"
                    ] += 1
                    changed = True

            if (
                class_id is None
                and school_id is not None
                and row[
                    "class_name_reported"
                ]
            ):
                candidates = con.execute(
                    """
                    SELECT id, name, code
                    FROM classes
                    WHERE school_id = ?
                      AND school_year_id = ?
                      AND is_active = 1
                    ORDER BY id
                    """,
                    (
                        int(school_id),
                        int(
                            row[
                                "school_year_id"
                            ]
                        ),
                    ),
                ).fetchall()

                wanted = norm(
                    row[
                        "class_name_reported"
                    ]
                )
                matches = [
                    int(item["id"])
                    for item in candidates
                    if (
                        norm(item["name"])
                        == wanted
                        or (
                            item["code"]
                            and norm(
                                item["code"]
                            )
                            == wanted
                        )
                    )
                ]

                if len(matches) == 1:
                    class_id = matches[0]
                    class_name = con.execute(
                        "SELECT name "
                        "FROM classes "
                        "WHERE id = ?",
                        (class_id,),
                    ).fetchone()[0]
                    result[
                        "class_linked"
                    ] += 1
                    changed = True

            grade = parse_grade(
                class_name
                or row[
                    "class_name_reported"
                ]
            )

            if (
                str(
                    row[
                        "learning_status"
                    ]
                    or ""
                ).strip().upper()
                == "DANG_HOC"
                and grade is not None
            ):
                desired_highest = max(
                    0,
                    grade - 1,
                )

                if (
                    highest
                    != desired_highest
                ):
                    highest = (
                        desired_highest
                    )
                    result[
                        "grade_corrected"
                    ] += 1
                    changed = True

                if grade >= 10:
                    desired_level = "THCS"
                elif grade >= 6:
                    desired_level = "TIEU_HOC"
                else:
                    desired_level = (
                        "CHUA_HOAN_THANH_TIEU_HOC"
                    )

                if (
                    level
                    != desired_level
                ):
                    level = desired_level
                    result[
                        "attainment_corrected"
                    ] += 1
                    changed = True

            ref_year = first_year(
                row["year_code"]
                or row["year_start"]
            )
            byear = birth_year(
                row["date_of_birth"]
            )

            if (
                ref_year is not None
                and byear is not None
            ):
                age = ref_year - byear
                if 0 <= age <= 120:
                    desired_target = (
                        1
                        if age >= 15
                        else 0
                    )

                    if (
                        target
                        != desired_target
                    ):
                        target = (
                            desired_target
                        )
                        if target:
                            result[
                                "xmc_to_no"
                            ] += 1
                        else:
                            result[
                                "xmc_to_yes"
                            ] += 1
                        changed = True

            if (
                target == 1
                and highest is not None
            ):
                desired_g3 = (
                    1
                    if int(highest) >= 3
                    else 0
                )
                desired_g5 = (
                    1
                    if int(highest) >= 5
                    else 0
                )
                desired_literacy = (
                    "KHONG_THUOC_DIEN"
                    if (
                        desired_g3 == 1
                        and desired_g5 == 1
                    )
                    else "THEO_DOI_XMC"
                )

                if g3 != desired_g3:
                    g3 = desired_g3
                    changed = True
                if g5 != desired_g5:
                    g5 = desired_g5
                    changed = True
                if (
                    literacy
                    != desired_literacy
                ):
                    literacy = (
                        desired_literacy
                    )
                    changed = True

            if changed:
                con.execute(
                    """
                    UPDATE survey_person_year_records
                    SET
                        school_id = ?,
                        class_id = ?,
                        highest_completed_grade = ?,
                        education_attainment_level = ?,
                        is_literacy_target = ?,
                        completed_grade_3 = ?,
                        completed_grade_5 = ?,
                        literacy_status = ?
                    WHERE id = ?
                    """,
                    (
                        school_id,
                        class_id,
                        highest,
                        level,
                        target,
                        g3,
                        g5,
                        literacy,
                        int(row["id"]),
                    ),
                )
                result["updated"] += 1

        con.commit()
        return result

    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def verify() -> None:
    access = read_text(ACCESS)
    surveys = read_text(SURVEYS)
    template = read_text(
        YEAR_TEMPLATE
    )

    for source, token in (
        (
            access,
            "BAI_13B_12_V2_3_2_"
            "EXTRACT_BATCH_ID_START",
        ),
        (
            surveys,
            "BAI_13B_12_V2_3_3_"
            "CURRENT_CLASS_SOURCE_START",
        ),
        (
            surveys,
            "BAI_13B_12_V2_3_3_"
            "XMC_BIDIRECTIONAL",
        ),
        (
            template,
            "BAI_13B_12_V2_3_3_"
            "XMC_SELECTED_YEAR_UI_START",
        ),
    ):
        if token not in source:
            raise RuntimeError(
                "Verifier thiếu: "
                + token
            )

    ast.parse(access)
    ast.parse(surveys)
    py_compile.compile(
        str(ACCESS),
        doraise=True,
    )
    py_compile.compile(
        str(SURVEYS),
        doraise=True,
    )
    Environment().parse(template)


def main() -> int:
    print("=" * 120)
    print(
        "BÀI 13B-12 V2.3.3 - "
        "XMC THEO NĂM HỌC + "
        "LỚP HIỆN TẠI + NÚT GV"
    )
    print("=" * 120)

    for path in (
        DB,
        ACCESS,
        SURVEYS,
        YEAR_TEMPLATE,
    ):
        if not path.exists():
            print(
                "DỪNG AN TOÀN: thiếu",
                path,
            )
            return 2

    before = state()
    print(
        "integrity_check:",
        before["integrity"],
    )
    print(
        "foreign_key_check:",
        before["fk"],
        "lỗi",
    )

    if (
        before["integrity"].lower()
        != "ok"
        or before["fk"] != 0
    ):
        print(
            "DỪNG: database chưa đạt."
        )
        return 3

    access = read_text(ACCESS)
    surveys = read_text(SURVEYS)
    template = read_text(
        YEAR_TEMPLATE
    )

    for token in (
        "BAI_13B_12_V2_3_1_"
        "GRADE_PARSER_START",
        "BAI_13B_11_15_2_4_7_1A_"
        "FORCE_XMC_AGE15_START",
    ):
        if token not in surveys:
            print(
                "DỪNG AN TOÀN: "
                "thiếu nền",
                token,
            )
            return 4

    if (
        "BAI_13B_12_V2_3_3_"
        "XMC_BIDIRECTIONAL"
        in surveys
    ):
        print(
            "V2.3.3 đã cài. "
            "Không cài lặp."
        )
        return 0

    try:
        new_access = patch_access(
            access
        )
        new_surveys = patch_surveys(
            surveys
        )
        new_template = patch_template(
            template
        )

        ast.parse(new_access)
        ast.parse(new_surveys)
        Environment().parse(
            new_template
        )

    except Exception as exc:
        print(
            "DỪNG AN TOÀN "
            "TRƯỚC KHI CÀI:"
        )
        print(
            type(exc).__name__ + ":",
            exc,
        )
        return 5

    EXPORTS.mkdir(
        parents=True,
        exist_ok=True,
    )
    BACKUP.mkdir(
        parents=True,
        exist_ok=False,
    )

    for path in (
        ACCESS,
        SURVEYS,
        YEAR_TEMPLATE,
    ):
        backup_file(path)
    backup_db()

    print("Backup:", BACKUP)

    try:
        write_text(
            ACCESS,
            new_access,
        )
        write_text(
            SURVEYS,
            new_surveys,
        )
        write_text(
            YEAR_TEMPLATE,
            new_template,
        )

        verify()
        normalized = normalize_db()

        after = state()

        if (
            after["integrity"].lower()
            != "ok"
        ):
            raise RuntimeError(
                "integrity_check "
                "không đạt sau cài."
            )
        if after["fk"] != 0:
            raise RuntimeError(
                "foreign_key_check "
                "có lỗi sau cài."
            )
        if (
            after["records"]
            != before["records"]
        ):
            raise RuntimeError(
                "Số year-record "
                "thay đổi ngoài dự kiến."
            )
        if (
            after["people"]
            != before["people"]
        ):
            raise RuntimeError(
                "Số nhân khẩu "
                "thay đổi ngoài dự kiến."
            )

        for cache in APP.rglob(
            "__pycache__"
        ):
            if cache.is_dir():
                shutil.rmtree(
                    cache,
                    ignore_errors=True,
                )

    except Exception as exc:
        print()
        print(
            "CÓ LỖI - "
            "ĐANG ROLLBACK..."
        )
        print(
            type(exc).__name__ + ":",
            exc,
        )

        for path in (
            ACCESS,
            SURVEYS,
            YEAR_TEMPLATE,
        ):
            restore_file(path)
        restore_db()

        print(
            "ĐÃ KHÔI PHỤC."
        )
        return 9

    REPORT.write_text(
        "\n".join(
            [
                "=" * 120,
                "BÁO CÁO CÀI "
                "BÀI 13B-12 V2.3.3",
                "=" * 120,
                (
                    "Thời gian: "
                    f"{datetime.now():%d/%m/%Y %H:%M:%S}"
                ),
                "",
                "ĐÃ SỬA:",
                "- Tích hợp luôn V2.3.2; "
                "không cần chạy V2.3.2 riêng.",
                "- XMC dùng năm học đang chọn.",
                "- >=15 tuổi => Có; <15 tuổi => Không.",
                "- Đang học lớp N => "
                "lớp cao nhất hoàn thành = N-1.",
                "- Nối school_id/class_id từ "
                "tên theo phiếu nếu khớp duy nhất.",
                "",
                "CHUẨN HÓA:",
                repr(normalized),
                "",
                (
                    "integrity_check: "
                    f"{after['integrity']}"
                ),
                (
                    "foreign_key_check: "
                    f"{after['fk']} lỗi"
                ),
                f"Backup: {BACKUP}",
            ]
        )
        + "\n",
        encoding="utf-8-sig",
    )

    print()
    print("=" * 120)
    print(
        "CÀI ĐẶT THÀNH CÔNG "
        "BÀI 13B-12 V2.3.3"
    )
    print("=" * 120)
    print(
        "Chuẩn hóa:",
        normalized,
    )
    print(
        "Báo cáo:",
        REPORT,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
