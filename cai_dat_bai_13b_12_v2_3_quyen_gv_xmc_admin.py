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

MENU = APP / "templates" / "partials" / "dropdown_menu_v1.html"
ACCESS = APP / "access_control.py"
ADMIN_TEMPLATE = APP / "templates" / "surveys" / "household_update_center_v1.html"
HOUSEHOLDS_TEMPLATE = APP / "templates" / "surveys" / "households.html"
AREA_TEMPLATE = APP / "templates" / "survey_teams" / "commune_areas_v2_2.html"
NEW_HOUSE_TEMPLATE = APP / "templates" / "surveys" / "new_household_team_v2_2.html"
TEAM_ROUTER = APP / "routers" / "survey_team_registration.py"
SURVEYS = APP / "routers" / "surveys.py"
YEAR_TEMPLATE = APP / "templates" / "surveys" / "year_records.html"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = EXPORTS / f"backup_bai_13b_12_v2_3_{STAMP}"
DB_BACKUP = BACKUP / "phocap.db"
REPORT = EXPORTS / f"bao_cao_cai_bai_13b_12_v2_3_{STAMP}.txt"

MARK = "BAI_13B_12_V2_3"

TEAM_ASSIGN_OLD = '    assignments = []\n    for row in assignment_rows:\n        item = dict(row)\n        item["area_type_label"] = labels.get(\n            str(item.get("area_type") or ""),\n            str(item.get("area_type") or ""),\n        )\n        item["remaining_count"] = max(\n            0,\n            int(item["household_quota"] or 0)\n            - int(item["actual_count"] or 0),\n        )\n        if item["remaining_count"] > 0:\n            assignments.append(item)\n\n    return dict(batch), dict(team), members, assignments\n'
TEAM_ASSIGN_NEW = '    # === BAI_13B_12_V2_3_TEACHER_AREA_SCOPE_START ===\n    assignments = []\n    for row in assignment_rows:\n        item = dict(row)\n        item["area_type_label"] = labels.get(\n            str(item.get("area_type") or ""),\n            str(item.get("area_type") or ""),\n        )\n        difference = (\n            int(item["household_quota"] or 0)\n            - int(item["actual_count"] or 0)\n        )\n        item["remaining_count"] = max(0, difference)\n        item["excess_count"] = max(0, -difference)\n        # Số hộ dự kiến/chỉ tiêu là kế hoạch, KHÔNG phải trần cấm nhập.\n        assignments.append(item)\n\n    # Tương thích luồng TEST/legacy: trước V2.2 có thể đã chia phiếu cho\n    # tổ rồi mới khai báo địa bàn. Nếu chưa có bảng giao địa bàn cho tổ,\n    # suy ra phạm vi của tổ từ các phiếu hiện có đã nối survey_form_areas.\n    if not assignments:\n        legacy_rows = db.execute(\n            text(\n                """\n                SELECT\n                    a.id AS area_id,\n                    a.name AS area_name,\n                    a.area_type,\n                    COUNT(tf.survey_form_id) AS actual_count\n                FROM survey_investigation_team_forms tf\n                JOIN survey_form_areas fa\n                  ON fa.survey_form_id = tf.survey_form_id\n                JOIN survey_commune_areas a\n                  ON a.id = fa.area_id\n                WHERE tf.team_id = :team_id\n                  AND a.is_active = 1\n                GROUP BY a.id, a.name, a.area_type\n                ORDER BY a.name COLLATE NOCASE, a.id\n                """\n            ),\n            {"team_id": int(team["id"])},\n        ).mappings().all()\n\n        for row in legacy_rows:\n            item = dict(row)\n            actual_count = int(item.get("actual_count") or 0)\n            item["household_quota"] = actual_count\n            item["remaining_count"] = 0\n            item["excess_count"] = 0\n            item["area_type_label"] = labels.get(\n                str(item.get("area_type") or ""),\n                str(item.get("area_type") or ""),\n            )\n            assignments.append(item)\n\n    return dict(batch), dict(team), members, assignments\n    # === BAI_13B_12_V2_3_TEACHER_AREA_SCOPE_END ===\n'
PERMISSION_OLD = '            "remaining_quota": sum(\n                int(item["remaining_count"])\n                for item in assignments\n            ),\n'
PERMISSION_NEW = '            "remaining_quota": sum(\n                int(item.get("remaining_count") or 0)\n                for item in assignments\n            ),\n            "excess_households": sum(\n                int(item.get("excess_count") or 0)\n                for item in assignments\n            ),\n'
CREATE_QUOTA_OLD = '    if assignment is None:\n        return RedirectResponse(\n            url=(\n                "/dieu-tra/phan-cong-to-dieu-tra/"\n                f"nhap-ho-moi/{batch_id}?status=quota_full"\n            ),\n            status_code=303,\n        )\n\n    quota = int(assignment["household_quota"] or 0)\n    actual_before = int(\n        db.execute(\n            text(\n                """\n                SELECT COUNT(*)\n                FROM survey_investigation_team_forms tf\n                JOIN survey_form_areas fa\n                  ON fa.survey_form_id = tf.survey_form_id\n                WHERE tf.team_id = :team_id\n                  AND fa.area_id = :area_id\n                """\n            ),\n            {\n                "team_id": int(team["id"]),\n                "area_id": int(area_id),\n            },\n        ).scalar()\n        or 0\n    )\n    if actual_before >= quota:\n        return RedirectResponse(\n            url=(\n                "/dieu-tra/phan-cong-to-dieu-tra/"\n                f"nhap-ho-moi/{batch_id}?status=quota_full"\n            ),\n            status_code=303,\n        )\n\n'
CREATE_QUOTA_NEW = '    if assignment is None:\n        return RedirectResponse(\n            url=(\n                "/dieu-tra/phan-cong-to-dieu-tra/"\n                f"nhap-ho-moi/{batch_id}?status=invalid_area"\n            ),\n            status_code=303,\n        )\n\n    # === BAI_13B_12_V2_3_NO_HOUSEHOLD_CAP_START ===\n    # Không chặn khi đạt/vượt số hộ dự kiến. Điều tra PCGD/XMC phải thu đủ\n    # hộ thực tế phát hiện ngoài địa bàn.\n    # === BAI_13B_12_V2_3_NO_HOUSEHOLD_CAP_END ===\n\n'
CREATE_FINAL_CAP_OLD = '        actual_after = int(\n            db.execute(\n                text(\n                    """\n                    SELECT COUNT(*)\n                    FROM survey_investigation_team_forms tf\n                    JOIN survey_form_areas fa\n                      ON fa.survey_form_id = tf.survey_form_id\n                    WHERE tf.team_id = :team_id\n                      AND fa.area_id = :area_id\n                    """\n                ),\n                {\n                    "team_id": int(team["id"]),\n                    "area_id": int(area_id),\n                },\n            ).scalar()\n            or 0\n        )\n        if actual_after > quota:\n            raise RuntimeError(\n                "Vượt chỉ tiêu hộ của tổ tại địa bàn."\n            )\n\n'
CREATE_FINAL_CAP_NEW = '        # === BAI_13B_12_V2_3_ALLOW_OVER_EXPECTED_START ===\n        # Không rollback khi số hộ thực tế vượt kế hoạch.\n        # === BAI_13B_12_V2_3_ALLOW_OVER_EXPECTED_END ===\n\n'

AREA_STATS_OLD = '            item["remaining_households"] = max(0, expected - actual)\n            item["progress_percent"] = (\n                min(100, round(actual * 100 / expected))\n                if expected\n                else 0\n            )\n'
AREA_STATS_NEW = '            difference = expected - actual\n            item["remaining_households"] = max(0, difference)\n            item["excess_households"] = max(0, -difference)\n            item["progress_percent"] = (\n                round(actual * 100 / expected)\n                if expected\n                else (100 if actual else 0)\n            )\n'
AREA_SUMMARY_OLD = '    area_summary["remaining_total"] = max(\n        0,\n        area_summary["expected_total"]\n        - area_summary["actual_total"],\n    )\n'
AREA_SUMMARY_NEW = '    total_difference = (\n        area_summary["expected_total"]\n        - area_summary["actual_total"]\n    )\n    area_summary["remaining_total"] = max(0, total_difference)\n    area_summary["excess_total"] = max(0, -total_difference)\n'
AREA_EXPECTED_BLOCK_OLD = '        actual_count = _b1322_int(\n            db.execute(\n                text(\n                    """\n                    SELECT COUNT(*)\n                    FROM survey_form_areas\n                    WHERE area_id = :area_id\n                    """\n                ),\n                {"area_id": area_id},\n            ).scalar()\n        )\n        if expected < actual_count:\n            return _b1322_redirect(\n                school_year_id=school_year_id,\n                batch_id=batch_id,\n                status="invalid",\n            )\n\n'
AREA_EXPECTED_BLOCK_NEW = '        # === BAI_13B_12_V2_3_EXPECTED_IS_PLAN_START ===\n        # Số hộ dự kiến là kế hoạch quản lý, có thể thấp hơn số hộ thực tế.\n        # Không chặn sửa danh mục chỉ vì thực tế đã vượt dự kiến.\n        # === BAI_13B_12_V2_3_EXPECTED_IS_PLAN_END ===\n\n'

VALIDATE_V21 = '    # === BAI_13B_12_V2_1_ATTAINMENT_VALIDATE_START ===\n    # Hai trường này áp dụng cho TOÀN BỘ thành viên hộ, không chỉ học sinh.\n    _b1312v21_grade_value = None\n    _b1312v21_grade_raw = str(\n        highest_completed_grade or ""\n    ).strip()\n\n    if not _b1312v21_grade_raw:\n        errors.append(\n            "Chưa khai báo lớp cao nhất đã hoàn thành."\n        )\n    else:\n        try:\n            _b1312v21_grade_value = int(\n                _b1312v21_grade_raw\n            )\n        except (TypeError, ValueError):\n            errors.append(\n                "Lớp cao nhất đã hoàn thành không hợp lệ."\n            )\n        else:\n            if not 0 <= _b1312v21_grade_value <= 12:\n                errors.append(\n                    "Lớp cao nhất đã hoàn thành phải từ 0 đến 12."\n                )\n\n    _b1312v21_level_value = str(\n        education_attainment_level\n        or "CHUA_XAC_DINH"\n    ).strip().upper()\n\n    _b1312v21_allowed_levels = {\n        "CHUA_XAC_DINH",\n        "CHUA_HOAN_THANH_TIEU_HOC",\n        "TIEU_HOC",\n        "THCS",\n        "THPT",\n        "TRUNG_CAP",\n        "CAO_DANG",\n        "DAI_HOC",\n        "SAU_DAI_HOC",\n        "KHAC",\n    }\n\n    if (\n        _b1312v21_level_value\n        not in _b1312v21_allowed_levels\n    ):\n        errors.append(\n            "Trình độ học vấn cao nhất không hợp lệ."\n        )\n        _b1312v21_level_value = "CHUA_XAC_DINH"\n    elif _b1312v21_level_value == "CHUA_XAC_DINH":\n        errors.append(\n            "Chưa khai báo trình độ học vấn cao nhất."\n        )\n    # === BAI_13B_12_V2_1_ATTAINMENT_VALIDATE_END ===\n\n'
VALIDATE_V23 = '    # === BAI_13B_12_V2_1_ATTAINMENT_VALIDATE_START ===\n    # Bài V2.3: nếu đang học và có lớp hiện tại thì cho phép suy ra lớp\n    # cao nhất đã hoàn thành ở bước sau, sau khi đã xác định selected_class.\n    _b1312v21_grade_value = None\n    _b1312v21_grade_raw = str(\n        highest_completed_grade or ""\n    ).strip()\n\n    if _b1312v21_grade_raw:\n        try:\n            _b1312v21_grade_value = int(\n                _b1312v21_grade_raw\n            )\n        except (TypeError, ValueError):\n            errors.append(\n                "Lớp cao nhất đã hoàn thành không hợp lệ."\n            )\n        else:\n            if not 0 <= _b1312v21_grade_value <= 12:\n                errors.append(\n                    "Lớp cao nhất đã hoàn thành phải từ 0 đến 12."\n                )\n                _b1312v21_grade_value = None\n\n    _b1312v21_level_value = str(\n        education_attainment_level\n        or "CHUA_XAC_DINH"\n    ).strip().upper()\n\n    _b1312v21_allowed_levels = {\n        "CHUA_XAC_DINH",\n        "CHUA_HOAN_THANH_TIEU_HOC",\n        "TIEU_HOC",\n        "THCS",\n        "THPT",\n        "TRUNG_CAP",\n        "CAO_DANG",\n        "DAI_HOC",\n        "SAU_DAI_HOC",\n        "KHAC",\n    }\n\n    if (\n        _b1312v21_level_value\n        not in _b1312v21_allowed_levels\n    ):\n        errors.append(\n            "Trình độ học vấn cao nhất không hợp lệ."\n        )\n        _b1312v21_level_value = "CHUA_XAC_DINH"\n    # === BAI_13B_12_V2_1_ATTAINMENT_VALIDATE_END ===\n'
INFERENCE_AFTER_CLASS = '    # === BAI_13B_12_V2_3_CLASS_TO_ATTAINMENT_START ===\n    _b1323_current_class_text = (\n        selected_class.name\n        if selected_class is not None\n        else class_name_reported\n    )\n    _b1323_current_grade = None\n    _b1323_class_match = re.search(\n        r"(?i)\\bl[oớ]p\\s*(1[0-2]|[1-9])\\b",\n        str(_b1323_current_class_text or ""),\n    )\n    if _b1323_class_match:\n        _b1323_current_grade = int(\n            _b1323_class_match.group(1)\n        )\n\n    if (\n        learning_status == "DANG_HOC"\n        and _b1323_current_grade is not None\n    ):\n        _b1323_inferred_completed = max(\n            0,\n            _b1323_current_grade - 1,\n        )\n        if _b1312v21_grade_value is None:\n            _b1312v21_grade_value = (\n                _b1323_inferred_completed\n            )\n\n        if _b1312v21_level_value == "CHUA_XAC_DINH":\n            if _b1323_current_grade >= 10:\n                # Đang học THPT => đã hoàn thành THCS.\n                _b1312v21_level_value = "THCS"\n            elif _b1323_current_grade >= 6:\n                # Đang học THCS => đã hoàn thành Tiểu học.\n                _b1312v21_level_value = "TIEU_HOC"\n            elif _b1323_current_grade >= 1:\n                _b1312v21_level_value = (\n                    "CHUA_HOAN_THANH_TIEU_HOC"\n                )\n\n    if _b1312v21_grade_value is None:\n        errors.append(\n            "Chưa khai báo lớp cao nhất đã hoàn thành."\n        )\n\n    if _b1312v21_level_value == "CHUA_XAC_DINH":\n        errors.append(\n            "Chưa khai báo trình độ học vấn cao nhất."\n        )\n    # === BAI_13B_12_V2_3_CLASS_TO_ATTAINMENT_END ===\n\n'
XMC_FORCE_FROM_GRADE = '        # === BAI_13B_12_V2_3_GRADE_TO_XMC_START ===\n        # completed_grade_3/5 là hệ quả trực tiếp của lớp cao nhất đã hoàn thành.\n        # Người 15+ vẫn thuộc phạm vi ĐIỀU TRA XMC theo quy tắc cũ;\n        # đây chỉ tự xác định mức biết chữ, không đổi quy tắc đối tượng.\n        if (\n            _b131132_is_literacy_target is True\n            and _b1312v21_grade_value is not None\n        ):\n            record.completed_grade_3 = (\n                _b1312v21_grade_value >= 3\n            )\n            record.completed_grade_5 = (\n                _b1312v21_grade_value >= 5\n            )\n        # === BAI_13B_12_V2_3_GRADE_TO_XMC_END ===\n\n'
YEAR_JS = '<!-- === BAI_13B_12_V2_3_CLASS_XMC_UI_START === -->\n<script>\n(function () {\n    "use strict";\n\n    function parseGrade(text) {\n        const match = String(text || "").match(/l[ớo]p\\s*(1[0-2]|[1-9])\\b/i);\n        return match ? Number(match[1]) : null;\n    }\n\n    function selectedClassText() {\n        const classSelect = document.getElementById("class_id");\n        const reported = document.getElementById("class_name_reported");\n\n        if (classSelect && classSelect.value) {\n            const option = classSelect.options[classSelect.selectedIndex];\n            if (option) return option.textContent || "";\n        }\n        return reported ? reported.value : "";\n    }\n\n    function setSelectValue(select, value) {\n        if (!select || value === null || value === undefined) return;\n        const exists = Array.from(select.options || []).some(function (o) {\n            return String(o.value) === String(value);\n        });\n        if (exists) {\n            select.value = String(value);\n            select.dispatchEvent(new Event("change", {bubbles: true}));\n        }\n    }\n\n    function applyEducationInference() {\n        const learning = document.getElementById("learning_status");\n        const highest = document.getElementById("highest_completed_grade");\n        const level = document.getElementById("education_attainment_level");\n        const g3 = document.getElementById("completed_grade_3");\n        const g5 = document.getElementById("completed_grade_5");\n\n        const currentGrade = parseGrade(selectedClassText());\n\n        if (\n            learning\n            && String(learning.value || "").toUpperCase() === "DANG_HOC"\n            && currentGrade !== null\n        ) {\n            const inferred = Math.max(0, currentGrade - 1);\n\n            if (highest && String(highest.value || "") === "") {\n                setSelectValue(highest, inferred);\n            }\n\n            if (\n                level\n                && String(level.value || "").toUpperCase() === "CHUA_XAC_DINH"\n            ) {\n                if (currentGrade >= 10) {\n                    setSelectValue(level, "THCS");\n                } else if (currentGrade >= 6) {\n                    setSelectValue(level, "TIEU_HOC");\n                } else if (currentGrade >= 1) {\n                    setSelectValue(level, "CHUA_HOAN_THANH_TIEU_HOC");\n                }\n            }\n        }\n\n        if (highest && String(highest.value || "") !== "") {\n            const completed = Number(highest.value);\n            if (Number.isFinite(completed)) {\n                setSelectValue(g3, completed >= 3 ? "CO" : "KHONG");\n                setSelectValue(g5, completed >= 5 ? "CO" : "KHONG");\n            }\n        }\n    }\n\n    document.addEventListener("DOMContentLoaded", function () {\n        ["class_id", "class_name_reported", "learning_status", "highest_completed_grade"]\n            .forEach(function (id) {\n                const element = document.getElementById(id);\n                if (!element) return;\n                element.addEventListener("change", applyEducationInference);\n                element.addEventListener("input", applyEducationInference);\n            });\n\n        applyEducationInference();\n        window.setTimeout(applyEducationInference, 150);\n        window.setTimeout(applyEducationInference, 500);\n    });\n})();\n</script>\n<!-- === BAI_13B_12_V2_3_CLASS_XMC_UI_END === -->\n'

ADMIN_NOTICE_BLOCK = '    <section class="panel">\n        <div class="notice info">\n            <strong>Nguyên tắc xử lý nhiều file:</strong> mỗi file được cấp một mã lần gửi riêng\n            <code>IMP-...</code>. Nhiều người có thể gửi trong cùng khoảng thời gian; mỗi file được\n            tiếp nhận, kiểm tra và lưu lịch sử độc lập. File lỗi không làm ảnh hưởng file đúng.\n        </div>\n        <div class="notice warn">\n            <strong>V1B đã cập nhật dữ liệu thật đối với file .xlsx đúng mẫu.</strong>\n            Hệ thống kiểm tra năm/xã, từng dòng, ngày sinh, số phiếu, trùng Số định danh/CCCD và xung đột CSDL.\n            Nếu có lỗi nghiêm trọng, <strong>không ghi bất kỳ dòng nào của file</strong>. Nhiều file được ghi lần lượt an toàn.\n            File <strong>.xls</strong> vẫn được nhận/lưu an toàn nhưng chưa ghi CSDL ở V1B; sẽ bổ sung bộ đọc .xls ở V1C và không chạy macro.\n        </div>\n        <div class="ref-grid">\n'
ADMIN_NOTICE_REPLACEMENT = '    <section class="panel">\n        <!-- === BAI_13B_12_V2_3_ADMIN_CLEAN_START === -->\n        <div class="ref-grid">\n'

CORE_TABLES = (
    "survey_batches",
    "households",
    "survey_forms",
    "survey_people",
    "survey_person_year_records",
    "survey_investigation_teams",
    "survey_investigation_team_members",
    "survey_investigation_team_forms",
    "survey_commune_areas",
    "survey_team_area_assignments",
    "survey_form_areas",
)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def write_text(path: Path, value: str) -> None:
    path.write_text(value, encoding="utf-8")


def backup_file(path: Path) -> None:
    if not path.exists():
        return
    target = BACKUP / path.relative_to(PROJECT)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, target)


def restore_file(path: Path) -> None:
    source = BACKUP / path.relative_to(PROJECT)
    if source.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, path)


def backup_database() -> None:
    src = sqlite3.connect(str(DB))
    dst = sqlite3.connect(str(DB_BACKUP))
    try:
        src.backup(dst)
        dst.commit()
    finally:
        dst.close()
        src.close()


def restore_database() -> None:
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


def db_snapshot() -> dict:
    con = sqlite3.connect(str(DB))
    try:
        integrity = str(
            con.execute("PRAGMA integrity_check").fetchone()[0]
        )
        fk_count = len(
            con.execute("PRAGMA foreign_key_check").fetchall()
        )
        existing = {
            row[0]
            for row in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        counts = {}
        for table in CORE_TABLES:
            if table in existing:
                counts[table] = int(
                    con.execute(
                        f'SELECT COUNT(*) FROM "{table}"'
                    ).fetchone()[0]
                )
        return {
            "integrity": integrity,
            "fk_count": fk_count,
            "tables": existing,
            "counts": counts,
        }
    finally:
        con.close()


def patch_menu(source: str) -> str:
    if f"{MARK}_UPDATE_MENU_ONLY_SO" in source:
        return source

    marker = "BAI_13B_12_V2_2_HIDE_UPDATE_XA_START"
    pos = source.find(marker)
    if pos < 0:
        raise RuntimeError(
            "Menu thiếu marker V2.2 ẩn cập nhật hộ."
        )

    start = max(0, pos - 300)
    end = min(len(source), pos + 900)
    window = source[start:end]

    old = (
        "{% if nguoi_dung and "
        "nguoi_dung.role_code not in ['GIAO_VIEN', 'XA'] %}"
    )
    if old not in window:
        raise RuntimeError(
            "Điều kiện menu Cập nhật dữ liệu hộ dân "
            "không còn đúng bản V2.2."
        )

    new = (
        "{# === "
        + MARK
        + "_UPDATE_MENU_ONLY_SO === #}\n"
        "{% if menu_role in ['ADMIN', 'SO'] %}"
    )
    window = window.replace(old, new, 1)
    return source[:start] + window + source[end:]


def patch_access(source: str) -> str:
    if f"{MARK}_UPDATE_ACCESS_ONLY_SO" in source:
        return source

    action_start = source.find(
        "# === BAI_13B_9_V1A_ACCESS_ACTION_START ==="
    )
    action_end = source.find(
        "# === BAI_13B_9_V1A_ACCESS_ACTION_END ===",
        action_start,
    )
    if action_start < 0 or action_end < 0:
        raise RuntimeError(
            "Không tìm thấy access action cập nhật hộ."
        )

    window = source[action_start:action_end]

    if "SCHOOL_ROLE_CODE," not in window:
        raise RuntimeError(
            "Access action không còn SCHOOL_ROLE_CODE như dự kiến."
        )
    window = window.replace(
        "                SCHOOL_ROLE_CODE,\n",
        "                # V2.3: Trường không truy cập cập nhật hộ tập trung.\n",
        1,
    )

    if "DEPARTMENT_ROLE_CODE," in window:
        window = window.replace(
            "                DEPARTMENT_ROLE_CODE,\n",
            "                # V2.3: chỉ ADMIN/SO cập nhật tập trung.\n",
            1,
        )

    window = window.replace(
        "                or role_code == SCHOOL_ROLE_CODE\n",
        "",
        1,
    )

    source = (
        source[:action_start]
        + window
        + source[action_end:]
    )

    scope_start = source.find(
        "# === BAI_13B_9_V1A_ACCESS_SCOPE_START ==="
    )
    scope_end = source.find(
        "# === BAI_13B_9_V1A_ACCESS_SCOPE_END ===",
        scope_start,
    )
    if scope_start < 0 or scope_end < 0:
        raise RuntimeError(
            "Không tìm thấy access scope cập nhật hộ."
        )

    scope_window = source[scope_start:scope_end]
    block_start = scope_window.find(
        '        if normalized_path.startswith('
        '"/dieu-tra/cap-nhat-ho-dan"):'
    )
    block_end = scope_window.find(
        "        # ADMIN/Sở",
        block_start,
    )

    if block_start < 0 or block_end < 0:
        raise RuntimeError(
            "Không xác định được block scope cập nhật hộ."
        )

    old_scope_tail = (
        "        # ADMIN/Sở và PHONG_BAN đã được "
        "cho qua ở đầu hàm.\n"
    )
    if not scope_window[block_end:].startswith(old_scope_tail):
        raise RuntimeError(
            "Comment scope ADMIN/Sở khác bản dự kiến."
        )

    replacement = (
        '        if normalized_path.startswith('
        '"/dieu-tra/cap-nhat-ho-dan"):\n'
        "            # V2.3: Xã/Trường/GV đều bị chặn; "
        "ADMIN/SO đã qua ở đầu hàm.\n"
        "            return False\n"
        "        # V2.3: Cập nhật hộ tập trung "
        "chỉ dành cho ADMIN/SO.\n"
    )

    scope_window = (
        scope_window[:block_start]
        + replacement
        + scope_window[
            block_end + len(old_scope_tail):
        ]
    )
    source = (
        source[:scope_start]
        + scope_window
        + source[scope_end:]
    )

    insert_at = source.find(
        "# === BAI_13B_9_V1A_ACCESS_ACTION_END ==="
    )
    source = (
        source[:insert_at]
        + "        # === "
        + MARK
        + "_UPDATE_ACCESS_ONLY_SO ===\n"
        + source[insert_at:]
    )
    return source


def patch_admin_template(source: str) -> str:
    if f"{MARK}_ADMIN_CLEAN_START" in source:
        return source

    if ADMIN_NOTICE_BLOCK not in source:
        raise RuntimeError(
            "Template ADMIN khác bản V1B dự kiến."
        )

    source = source.replace(
        ADMIN_NOTICE_BLOCK,
        ADMIN_NOTICE_REPLACEMENT,
        1,
    )

    source = source.replace(
        '        <div style="font-size:13px;font-weight:800;'
        'letter-spacing:.08em">BÀI 13B-9 V1B · '
        'CẬP NHẬT DỮ LIỆU HỘ DÂN</div>\n',
        "",
        1,
    )
    source = source.replace(
        "<h1>Kiểm tra và cập nhật dữ liệu Excel an toàn</h1>",
        "<h1>Cập nhật dữ liệu hộ dân từ Excel</h1>",
        1,
    )
    source = source.replace(
        "<p>{{ scope_label }} · Nhận độc lập từng file, "
        "chống gửi trùng, lưu lịch sử và không chạy macro.</p>",
        "<p>{{ scope_label }}</p>",
        1,
    )

    for note in (
        '                <p class="small">Không tô màu, không cố định năm. '
        'Năm và xã lấy theo đợt đang chọn ở phía dưới.</p>\n',
        '                <p class="small">Mẫu dùng làm chuẩn cho bản in '
        'phiếu thực địa A4 nằm ngang.</p>\n',
        '                <div class="small" style="margin-top:6px">'
        'Tối đa 25 MB mỗi file. Có thể chọn nhiều file; hệ thống gửi '
        'từng file độc lập.</div>\n',
        '                <p class="small">Thống kê theo toàn bộ thành viên '
        'của hộ, không giới hạn theo cấp học của giáo viên.</p>\n',
    ):
        source = source.replace(note, "", 1)

    anchor = (
        "        </div>\n"
        "    </section>\n\n"
        '    <section class="panel">\n'
        '        <h2 style="margin-top:0">Chọn phạm vi</h2>'
    )
    if anchor not in source:
        raise RuntimeError(
            "Không xác định được cuối khối mẫu tải ADMIN."
        )

    source = source.replace(
        anchor,
        "        </div>\n"
        "        <!-- === "
        + MARK
        + "_ADMIN_CLEAN_END === -->\n"
        "    </section>\n\n"
        '    <section class="panel">\n'
        '        <h2 style="margin-top:0">Chọn phạm vi</h2>',
        1,
    )
    return source


def patch_team_router(source: str) -> str:
    if f"{MARK}_TEACHER_AREA_SCOPE_START" not in source:
        if TEAM_ASSIGN_OLD not in source:
            raise RuntimeError(
                "Không tìm thấy block assignments V2.2."
            )
        source = source.replace(
            TEAM_ASSIGN_OLD,
            TEAM_ASSIGN_NEW,
            1,
        )

    if f"{MARK}_NO_HOUSEHOLD_CAP_START" not in source:
        if CREATE_QUOTA_OLD not in source:
            raise RuntimeError(
                "Không tìm thấy block chặn quota V2.2."
            )
        source = source.replace(
            CREATE_QUOTA_OLD,
            CREATE_QUOTA_NEW,
            1,
        )

    if f"{MARK}_ALLOW_OVER_EXPECTED_START" not in source:
        if CREATE_FINAL_CAP_OLD not in source:
            raise RuntimeError(
                "Không tìm thấy block rollback vượt quota V2.2."
            )
        source = source.replace(
            CREATE_FINAL_CAP_OLD,
            CREATE_FINAL_CAP_NEW,
            1,
        )

    if '"excess_households": sum(' not in source:
        if PERMISSION_OLD not in source:
            raise RuntimeError(
                "Không tìm thấy JSON remaining_quota V2.2."
            )
        source = source.replace(
            PERMISSION_OLD,
            PERMISSION_NEW,
            1,
        )

    source = source.replace(
        '"quota_full": "Địa bàn đã đủ chỉ tiêu hộ của tổ; '
        'không thể tạo thêm hộ.",',
        '"quota_full": "Chỉ tiêu dự kiến đã đạt; '
        'V2.3 vẫn cho phép nhập đủ hộ thực tế.",\n'
        '        "invalid_area": "Địa bàn này chưa thuộc '
        'phạm vi được giao cho tổ.",',
        1,
    )

    return source


def patch_area_router(source: str) -> str:
    if f"{MARK}_AREA_STATS" not in source:
        if AREA_STATS_OLD not in source:
            raise RuntimeError(
                "Không tìm thấy block thống kê địa bàn V2.2."
            )
        source = source.replace(
            AREA_STATS_OLD,
            "            # === "
            + MARK
            + "_AREA_STATS ===\n"
            + AREA_STATS_NEW,
            1,
        )

    if '"excess_total"' not in source:
        if AREA_SUMMARY_OLD not in source:
            raise RuntimeError(
                "Không tìm thấy block tổng thống kê địa bàn."
            )
        source = source.replace(
            AREA_SUMMARY_OLD,
            AREA_SUMMARY_NEW,
            1,
        )

    if f"{MARK}_EXPECTED_IS_PLAN_START" not in source:
        if AREA_EXPECTED_BLOCK_OLD not in source:
            raise RuntimeError(
                "Không tìm thấy block expected < actual V2.2."
            )
        source = source.replace(
            AREA_EXPECTED_BLOCK_OLD,
            AREA_EXPECTED_BLOCK_NEW,
            1,
        )

    return source


def patch_area_template(source: str) -> str:
    if f"{MARK}_AREA_OVER_UI" in source:
        return source

    old_stat = (
        '<div class="stat"><small>Còn thiếu</small>'
        '<strong>{{ area_summary.remaining_total }}</strong></div>'
    )
    new_stat = (
        '<div class="stat"><small>'
        '{% if area_summary.excess_total %}'
        'Vượt dự kiến{% else %}Còn thiếu{% endif %}'
        '</small><strong>'
        '{% if area_summary.excess_total %}'
        '+{{ area_summary.excess_total }}'
        '{% else %}{{ area_summary.remaining_total }}{% endif %}'
        '</strong></div>'
    )
    if old_stat not in source:
        raise RuntimeError(
            "Template địa bàn thiếu ô Còn thiếu V2.2."
        )
    source = source.replace(old_stat, new_stat, 1)

    source = source.replace(
        '<th class="num">Còn thiếu</th>',
        '<th class="num">Còn thiếu / Vượt</th>',
        1,
    )

    old_cell = (
        '<td class="num">{{ a.remaining_households }}</td>'
    )
    new_cell = (
        '<td class="num">'
        '{% if a.excess_households %}'
        '<strong>Vượt {{ a.excess_households }}</strong>'
        '{% else %}{{ a.remaining_households }}{% endif %}'
        '</td>'
    )
    if old_cell not in source:
        raise RuntimeError(
            "Template địa bàn thiếu cell remaining."
        )
    source = source.replace(old_cell, new_cell, 1)

    marker = (
        "<!-- === "
        + MARK
        + "_AREA_OVER_UI === -->\n"
    )
    pos = source.find('<section class="b1322-panel">')
    if pos < 0:
        raise RuntimeError(
            "Không tìm thấy panel template địa bàn."
        )
    source = source[:pos] + marker + source[pos:]
    return source


def patch_new_house_template(source: str) -> str:
    if f"{MARK}_NEW_HOUSE_UI" in source:
        return source

    old = (
        "Chỉ tiêu của tổ: {{ a.household_quota }} hộ · "
        "Đã nhập: {{ a.actual_count }} · "
        "Còn: {{ a.remaining_count }}"
    )
    new = (
        "Chỉ tiêu kế hoạch của tổ: "
        "{{ a.household_quota }} hộ · "
        "Đã nhập: {{ a.actual_count }}"
        "{% if a.excess_count %} · "
        "<strong>Vượt {{ a.excess_count }}</strong>"
        "{% elif a.remaining_count %} · "
        "Còn theo kế hoạch: {{ a.remaining_count }}"
        "{% else %} · Đã đạt kế hoạch; "
        "vẫn được nhập đủ hộ thực tế{% endif %}"
    )
    if old not in source:
        raise RuntimeError(
            "Template nhập hộ mới thiếu dòng quota V2.2."
        )
    source = source.replace(old, new, 1)
    source = source.replace(
        '<section class="head">',
        "<!-- === "
        + MARK
        + "_NEW_HOUSE_UI === -->\n"
        '<section class="head">',
        1,
    )
    return source


def patch_households_button(source: str) -> str:
    if f"{MARK}_BUTTON_TITLE" in source:
        return source

    old = (
        '            link.title =\n'
        '                "Tổ " + data.team_number\n'
        '                + " · còn " + data.remaining_quota + " hộ";\n'
    )
    new = (
        "            // === BAI_13B_12_V2_3_BUTTON_TITLE ===\n"
        "            if (Number(data.excess_households || 0) > 0) {\n"
        "                link.title =\n"
        '                    "Tổ " + data.team_number\n'
        '                    + " · đã vượt " + data.excess_households\n'
        '                    + " hộ so với kế hoạch; vẫn nhập đủ thực tế";\n'
        "            } else {\n"
        "                link.title =\n"
        '                    "Tổ " + data.team_number\n'
        '                    + " · còn " + data.remaining_quota\n'
        '                    + " hộ theo kế hoạch";\n'
        "            }\n"
    )
    if old not in source:
        raise RuntimeError(
            "households.html thiếu JS title V2.2."
        )
    return source.replace(old, new, 1)


def patch_surveys_xmc(source: str) -> str:
    if f"{MARK}_CLASS_TO_ATTAINMENT_START" not in source:
        if VALIDATE_V21 not in source:
            raise RuntimeError(
                "Không tìm thấy block validate V2.1."
            )
        source = source.replace(
            VALIDATE_V21,
            VALIDATE_V23,
            1,
        )

        anchor = (
            "    if selected_school is not None:\n"
            "        school_name_reported = selected_school.name\n"
            "    if selected_class is not None:\n"
            "        class_name_reported = selected_class.name\n"
            "\n"
        )
        if anchor not in source:
            raise RuntimeError(
                "Không tìm thấy điểm suy luận sau selected_class."
            )
        source = source.replace(
            anchor,
            anchor + INFERENCE_AFTER_CLASS,
            1,
        )

    if f"{MARK}_GRADE_TO_XMC_START" not in source:
        derive_marker = (
            "        # === BAI_13B_11_15_2_4_7_1B_"
            "DERIVE_LITERACY_STATUS_START ==="
        )
        pos = source.find(derive_marker)
        if pos < 0:
            raise RuntimeError(
                "Không tìm thấy marker derive XMC 1B."
            )
        source = (
            source[:pos]
            + XMC_FORCE_FROM_GRADE
            + source[pos:]
        )

    return source


def patch_year_template(source: str) -> str:
    if f"{MARK}_CLASS_XMC_UI_START" not in source:
        body = source.rfind("</body>")
        if body < 0:
            raise RuntimeError(
                "year_records.html thiếu </body>."
            )
        source = (
            source[:body]
            + YEAR_JS
            + source[body:]
        )

    source = source.replace(
        "1. Đối tượng điều tra Xóa mù chữ",
        "1. Phạm vi điều tra Xóa mù chữ",
        1,
    )
    source = source.replace(
        "Xác định đối tượng này có thuộc phạm vi điều tra "
        "Xóa mù chữ trong năm học đang chọn hay không.",
        "Người từ 15 tuổi trở lên vẫn thuộc phạm vi thống kê "
        "Xóa mù chữ theo quy tắc cũ. Thuộc phạm vi điều tra "
        "không đồng nghĩa là mù chữ.",
        1,
    )
    source = source.replace(
        "Đối tượng điều tra Xóa mù chữ",
        "Thuộc phạm vi điều tra Xóa mù chữ (theo tuổi)",
        1,
    )
    source = source.replace(
        "Từ 15 tuổi trở lên: bắt buộc thuộc diện điều tra Xóa mù chữ.",
        "Từ 15 tuổi trở lên: thuộc phạm vi điều tra XMC; "
        "mức biết chữ được suy ra riêng từ trình độ/lớp đã hoàn thành.",
        1,
    )
    return source


def normalize_text(value) -> str:
    return " ".join(
        str(value or "").strip().casefold().split()
    )


def parse_grade(value) -> int | None:
    match = re.search(
        r"(?i)\bl[oớ]p\s*(1[0-2]|[1-9])\b",
        str(value or ""),
    )
    return int(match.group(1)) if match else None


def backfill_v23_data() -> dict:
    con = sqlite3.connect(str(DB))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")

    result = {
        "form_area_linked": 0,
        "team_area_linked": 0,
        "year_records_normalized": 0,
    }

    try:
        tables = {
            row[0]
            for row in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }

        required = {
            "survey_commune_areas",
            "survey_team_area_assignments",
            "survey_form_areas",
            "survey_forms",
            "survey_batches",
            "households",
            "survey_investigation_teams",
            "survey_investigation_team_forms",
            "survey_person_year_records",
        }
        missing = required - tables
        if missing:
            raise RuntimeError(
                "Thiếu bảng V2.2: "
                + ", ".join(sorted(missing))
            )

        # 1. Nối phiếu TEST/legacy đã import vào địa bàn V2.2
        # khi chỉ có một địa bàn khớp chắc chắn.
        rows = con.execute(
            """
            SELECT
                sf.id AS survey_form_id,
                sb.commune_id,
                sb.school_year_id,
                h.hamlet_name,
                sf.hamlet_name_snapshot,
                h.address,
                sf.address_snapshot
            FROM survey_forms sf
            JOIN survey_batches sb
              ON sb.id = sf.survey_batch_id
            JOIN households h
              ON h.id = sf.household_id
            LEFT JOIN survey_form_areas fa
              ON fa.survey_form_id = sf.id
            WHERE fa.id IS NULL
            ORDER BY sf.id
            """
        ).fetchall()

        now = datetime.now().isoformat(sep=" ")

        for row in rows:
            areas = con.execute(
                """
                SELECT id, name
                FROM survey_commune_areas
                WHERE commune_id = ?
                  AND school_year_id = ?
                  AND is_active = 1
                ORDER BY id
                """,
                (
                    int(row["commune_id"]),
                    int(row["school_year_id"]),
                ),
            ).fetchall()

            if not areas:
                continue

            hamlet = normalize_text(row["hamlet_name"])
            snapshot = normalize_text(
                row["hamlet_name_snapshot"]
            )
            address = normalize_text(row["address"])
            address_snapshot = normalize_text(
                row["address_snapshot"]
            )

            scored = []
            for area in areas:
                name = normalize_text(area["name"])
                if not name:
                    continue

                score = 0
                if hamlet and hamlet == name:
                    score = max(score, 1000)
                if snapshot and snapshot == name:
                    score = max(score, 900)
                if address and name in address:
                    score = max(score, 100 + len(name))
                if (
                    address_snapshot
                    and name in address_snapshot
                ):
                    score = max(score, 90 + len(name))

                if score:
                    scored.append(
                        (score, int(area["id"]))
                    )

            if not scored:
                continue

            scored.sort(reverse=True)
            best_score = scored[0][0]
            best = [
                area_id
                for score, area_id in scored
                if score == best_score
            ]
            if len(best) != 1:
                continue

            con.execute(
                """
                INSERT INTO survey_form_areas (
                    survey_form_id,
                    area_id,
                    created_at
                ) VALUES (?, ?, ?)
                """,
                (
                    int(row["survey_form_id"]),
                    best[0],
                    now,
                ),
            )
            result["form_area_linked"] += 1

        # 2. Tổ đã có phiếu nhưng chưa có giao địa bàn:
        # suy ra địa bàn từ chính phiếu đã phân công.
        teams = con.execute(
            """
            SELECT t.id
            FROM survey_investigation_teams t
            WHERE NOT EXISTS (
                SELECT 1
                FROM survey_team_area_assignments ta
                WHERE ta.team_id = t.id
            )
            ORDER BY t.id
            """
        ).fetchall()

        for team in teams:
            grouped = con.execute(
                """
                SELECT
                    fa.area_id,
                    COUNT(*) AS form_count
                FROM survey_investigation_team_forms tf
                JOIN survey_form_areas fa
                  ON fa.survey_form_id = tf.survey_form_id
                WHERE tf.team_id = ?
                GROUP BY fa.area_id
                ORDER BY fa.area_id
                """,
                (int(team["id"]),),
            ).fetchall()

            for item in grouped:
                count = int(
                    item["form_count"] or 0
                )
                if count <= 0:
                    continue

                con.execute(
                    """
                    INSERT INTO survey_team_area_assignments (
                        team_id,
                        area_id,
                        household_quota,
                        notes,
                        created_by_user_id,
                        created_at,
                        updated_at
                    ) VALUES (?, ?, ?, ?, NULL, ?, ?)
                    """,
                    (
                        int(team["id"]),
                        int(item["area_id"]),
                        count,
                        "[V2.3] Tự nối từ phiếu TEST/legacy "
                        "đã phân công.",
                        now,
                        now,
                    ),
                )
                result["team_area_linked"] += 1

        # 3. Chuẩn hóa year-record hiện có khi suy ra chắc chắn.
        year_rows = con.execute(
            """
            SELECT
                spr.id,
                spr.learning_status,
                spr.highest_completed_grade,
                spr.education_attainment_level,
                spr.is_literacy_target,
                spr.completed_grade_3,
                spr.completed_grade_5,
                spr.literacy_status,
                spr.class_name_reported,
                c.name AS class_name
            FROM survey_person_year_records spr
            LEFT JOIN classes c
              ON c.id = spr.class_id
            ORDER BY spr.id
            """
        ).fetchall()

        for row in year_rows:
            learning = str(
                row["learning_status"] or ""
            ).strip().upper()
            current_grade = parse_grade(
                row["class_name"]
                or row["class_name_reported"]
            )

            highest = row["highest_completed_grade"]
            level = str(
                row["education_attainment_level"]
                or "CHUA_XAC_DINH"
            ).strip().upper()

            changed = False

            if (
                highest is None
                and learning == "DANG_HOC"
                and current_grade is not None
            ):
                highest = max(
                    0,
                    current_grade - 1,
                )
                changed = True

            if (
                level == "CHUA_XAC_DINH"
                and learning == "DANG_HOC"
                and current_grade is not None
            ):
                if current_grade >= 10:
                    level = "THCS"
                elif current_grade >= 6:
                    level = "TIEU_HOC"
                elif current_grade >= 1:
                    level = (
                        "CHUA_HOAN_THANH_TIEU_HOC"
                    )
                changed = True

            g3 = row["completed_grade_3"]
            g5 = row["completed_grade_5"]
            literacy = str(
                row["literacy_status"]
                or "CHUA_XAC_DINH"
            )

            if (
                row["is_literacy_target"] == 1
                and highest is not None
            ):
                desired_g3 = (
                    1 if int(highest) >= 3 else 0
                )
                desired_g5 = (
                    1 if int(highest) >= 5 else 0
                )
                desired_literacy = (
                    "KHONG_THUOC_DIEN"
                    if desired_g3 == 1
                    and desired_g5 == 1
                    else "THEO_DOI_XMC"
                )

                if (
                    g3 != desired_g3
                    or g5 != desired_g5
                    or literacy != desired_literacy
                ):
                    g3 = desired_g3
                    g5 = desired_g5
                    literacy = desired_literacy
                    changed = True

            if changed:
                con.execute(
                    """
                    UPDATE survey_person_year_records
                    SET
                        highest_completed_grade = ?,
                        education_attainment_level = ?,
                        completed_grade_3 = ?,
                        completed_grade_5 = ?,
                        literacy_status = ?
                    WHERE id = ?
                    """,
                    (
                        highest,
                        level,
                        g3,
                        g5,
                        literacy,
                        int(row["id"]),
                    ),
                )
                result[
                    "year_records_normalized"
                ] += 1

        con.commit()
        return result

    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def verify_source() -> None:
    menu = read_text(MENU)
    access = read_text(ACCESS)
    admin = read_text(ADMIN_TEMPLATE)
    team = read_text(TEAM_ROUTER)
    area_template = read_text(AREA_TEMPLATE)
    new_house = read_text(NEW_HOUSE_TEMPLATE)
    households = read_text(HOUSEHOLDS_TEMPLATE)
    surveys = read_text(SURVEYS)
    year_template = read_text(YEAR_TEMPLATE)

    required = [
        (menu, f"{MARK}_UPDATE_MENU_ONLY_SO"),
        (access, f"{MARK}_UPDATE_ACCESS_ONLY_SO"),
        (admin, f"{MARK}_ADMIN_CLEAN_START"),
        (team, f"{MARK}_TEACHER_AREA_SCOPE_START"),
        (team, f"{MARK}_NO_HOUSEHOLD_CAP_START"),
        (team, f"{MARK}_AREA_STATS"),
        (area_template, f"{MARK}_AREA_OVER_UI"),
        (new_house, f"{MARK}_NEW_HOUSE_UI"),
        (households, f"{MARK}_BUTTON_TITLE"),
        (surveys, f"{MARK}_CLASS_TO_ATTAINMENT_START"),
        (surveys, f"{MARK}_GRADE_TO_XMC_START"),
        (year_template, f"{MARK}_CLASS_XMC_UI_START"),
        (
            surveys,
            "BAI_13B_11_15_2_4_7_1A_"
            "FORCE_XMC_AGE15_START",
        ),
        (
            surveys,
            "BAI_13B_11_15_2_4_7_1B_"
            "DERIVE_LITERACY_STATUS_START",
        ),
        (
            surveys,
            "BAI_13B_12_V2_1_ATTAINMENT_SAVE_START",
        ),
    ]
    for source, token in required:
        if token not in source:
            raise RuntimeError(
                "Verifier thiếu marker: " + token
            )

    if "2.2.8." in menu:
        raise RuntimeError(
            "Không được tạo menu 2.2.8."
        )

    if "Nguyên tắc xử lý nhiều file:" in admin:
        raise RuntimeError(
            "ADMIN vẫn còn chú thích xử lý nhiều file."
        )
    if "V1B đã cập nhật dữ liệu thật" in admin:
        raise RuntimeError(
            "ADMIN vẫn còn chú thích V1B dài."
        )

    ast.parse(access)
    ast.parse(team)
    ast.parse(surveys)

    py_compile.compile(str(ACCESS), doraise=True)
    py_compile.compile(str(TEAM_ROUTER), doraise=True)
    py_compile.compile(str(SURVEYS), doraise=True)

    env = Environment()
    for source in (
        menu,
        admin,
        area_template,
        new_house,
        households,
        year_template,
    ):
        env.parse(source)


def clear_cache() -> None:
    for cache in APP.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(
                cache,
                ignore_errors=True,
            )


def main() -> int:
    print("=" * 120)
    print(
        "BÀI 13B-12 V2.3 - QUYỀN CẬP NHẬT HỘ + "
        "GV NHẬP HỘ MỚI + SUY LUẬN TRÌNH ĐỘ/XMC"
    )
    print("=" * 120)
    print("Dự án:", PROJECT)
    print()

    required_paths = (
        DB,
        MENU,
        ACCESS,
        ADMIN_TEMPLATE,
        HOUSEHOLDS_TEMPLATE,
        AREA_TEMPLATE,
        NEW_HOUSE_TEMPLATE,
        TEAM_ROUTER,
        SURVEYS,
        YEAR_TEMPLATE,
    )
    for path in required_paths:
        if not path.exists():
            print(
                "DỪNG AN TOÀN: thiếu",
                path,
            )
            return 2

    before = db_snapshot()
    print(
        "integrity_check:",
        before["integrity"],
    )
    print(
        "foreign_key_check:",
        before["fk_count"],
        "lỗi",
    )

    if (
        before["integrity"].lower() != "ok"
        or before["fk_count"] != 0
    ):
        print(
            "DỪNG: database chưa đạt kiểm tra."
        )
        return 3

    preflight_tokens = (
        (
            read_text(TEAM_ROUTER),
            "BAI_13B_12_V2_2_TEAM_NEW_HOUSEHOLD_START",
        ),
        (
            read_text(TEAM_ROUTER),
            "BAI_13B_12_V2_2_AREA_WORKFLOW_START",
        ),
        (
            read_text(HOUSEHOLDS_TEMPLATE),
            "BAI_13B_12_V2_2_NEW_HOUSE_BUTTON",
        ),
        (
            read_text(SURVEYS),
            "BAI_13B_12_V2_1_ATTAINMENT_VALIDATE_START",
        ),
        (
            read_text(YEAR_TEMPLATE),
            "BAI_13B_11_15_2_4_7_1B_"
            "DERIVED_STATUS_UI_START",
        ),
    )
    for source, token in preflight_tokens:
        if token not in source:
            print(
                "DỪNG AN TOÀN: thiếu nền",
                token,
            )
            return 4

    if (
        f"{MARK}_CLASS_TO_ATTAINMENT_START"
        in read_text(SURVEYS)
    ):
        print(
            "V2.3 đã có trong source. "
            "Không cài lặp."
        )
        return 0

    try:
        menu_new = patch_menu(
            read_text(MENU)
        )
        access_new = patch_access(
            read_text(ACCESS)
        )
        admin_new = patch_admin_template(
            read_text(ADMIN_TEMPLATE)
        )

        team_new = patch_team_router(
            read_text(TEAM_ROUTER)
        )
        team_new = patch_area_router(
            team_new
        )

        area_template_new = patch_area_template(
            read_text(AREA_TEMPLATE)
        )
        new_house_new = patch_new_house_template(
            read_text(NEW_HOUSE_TEMPLATE)
        )
        households_new = patch_households_button(
            read_text(HOUSEHOLDS_TEMPLATE)
        )
        surveys_new = patch_surveys_xmc(
            read_text(SURVEYS)
        )
        year_template_new = patch_year_template(
            read_text(YEAR_TEMPLATE)
        )

        ast.parse(access_new)
        ast.parse(team_new)
        ast.parse(surveys_new)

        env = Environment()
        for source in (
            menu_new,
            admin_new,
            area_template_new,
            new_house_new,
            households_new,
            year_template_new,
        ):
            env.parse(source)

    except Exception as exc:
        print(
            "DỪNG AN TOÀN TRƯỚC KHI CÀI:"
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

    touched = (
        MENU,
        ACCESS,
        ADMIN_TEMPLATE,
        HOUSEHOLDS_TEMPLATE,
        AREA_TEMPLATE,
        NEW_HOUSE_TEMPLATE,
        TEAM_ROUTER,
        SURVEYS,
        YEAR_TEMPLATE,
    )
    for path in touched:
        backup_file(path)
    backup_database()

    print("Backup:", BACKUP)
    print()

    try:
        write_text(MENU, menu_new)
        write_text(ACCESS, access_new)
        write_text(ADMIN_TEMPLATE, admin_new)
        write_text(TEAM_ROUTER, team_new)
        write_text(
            AREA_TEMPLATE,
            area_template_new,
        )
        write_text(
            NEW_HOUSE_TEMPLATE,
            new_house_new,
        )
        write_text(
            HOUSEHOLDS_TEMPLATE,
            households_new,
        )
        write_text(
            SURVEYS,
            surveys_new,
        )
        write_text(
            YEAR_TEMPLATE,
            year_template_new,
        )

        verify_source()

        normalization = backfill_v23_data()

        after = db_snapshot()

        if after["integrity"].lower() != "ok":
            raise RuntimeError(
                "integrity_check không đạt sau cài."
            )
        if after["fk_count"] != 0:
            raise RuntimeError(
                "foreign_key_check có lỗi sau cài."
            )

        for table in (
            "survey_batches",
            "households",
            "survey_forms",
            "survey_people",
            "survey_person_year_records",
            "survey_investigation_teams",
            "survey_investigation_team_members",
            "survey_investigation_team_forms",
        ):
            if (
                before["counts"].get(table)
                != after["counts"].get(table)
            ):
                raise RuntimeError(
                    "Số dòng bảng lõi "
                    + table
                    + " thay đổi ngoài dự kiến."
                )

        clear_cache()

    except Exception as exc:
        print()
        print(
            "CÓ LỖI - ĐANG ROLLBACK "
            "SOURCE + DATABASE..."
        )
        print(
            type(exc).__name__ + ":",
            exc,
        )

        for path in touched:
            restore_file(path)
        restore_database()
        clear_cache()

        print("ĐÃ KHÔI PHỤC.")
        print("Backup:", BACKUP)
        return 9

    lines = [
        "=" * 120,
        "BÁO CÁO CÀI BÀI 13B-12 V2.3",
        "=" * 120,
        (
            "Thời gian: "
            f"{datetime.now():%d/%m/%Y %H:%M:%S}"
        ),
        f"Dự án: {PROJECT}",
        "",
        "1. QUYỀN / ADMIN",
        "- Cập nhật dữ liệu hộ dân chỉ còn ADMIN/SO.",
        "- Xã, Trường, Giáo viên bị ẩn menu và chặn route.",
        "- Xóa các chú thích kỹ thuật dài trên màn hình ADMIN.",
        "",
        "2. GIÁO VIÊN TẠO HỘ MỚI",
        "- GV thuộc tổ SENT + có địa bàn được giao thấy nút tại 2.2.1.",
        "- Đạt/vượt số hộ dự kiến KHÔNG làm ẩn nút.",
        "- Hộ thực tế vượt kế hoạch vẫn được tạo và gắn tổ.",
        "- Hỗ trợ nối địa bàn/tổ cho dữ liệu TEST/legacy.",
        "",
        "3. TRÌNH ĐỘ / XMC",
        "- Giữ nguyên quy tắc >=15 tuổi thuộc phạm vi điều tra XMC.",
        "- Thuộc phạm vi XMC không đồng nghĩa mù chữ.",
        "- Đang học lớp N => nếu trống, lớp hoàn thành = N-1.",
        "- Đang học lớp 10 => hoàn thành lớp 9; grade3/grade5 = Có.",
        "- Tình trạng biết chữ vẫn lấy grade3/grade5 theo quy tắc cũ.",
        "",
        "4. CHUẨN HÓA DỮ LIỆU HIỆN CÓ",
        (
            "- Nối survey_form_areas: "
            f"{normalization['form_area_linked']}"
        ),
        (
            "- Nối survey_team_area_assignments: "
            f"{normalization['team_area_linked']}"
        ),
        (
            "- Chuẩn hóa year-record: "
            f"{normalization['year_records_normalized']}"
        ),
        "",
        (
            "integrity_check: "
            f"{after['integrity']}"
        ),
        (
            "foreign_key_check: "
            f"{after['fk_count']} lỗi"
        ),
        f"Backup: {BACKUP}",
    ]

    REPORT.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8-sig",
    )

    print("=" * 120)
    print(
        "CÀI ĐẶT THÀNH CÔNG "
        "BÀI 13B-12 V2.3"
    )
    print("=" * 120)
    print(
        " - ADMIN/SO: giữ Cập nhật dữ liệu hộ dân; "
        "giao diện đã gọn."
    )
    print(
        " - Xã/Trường/GV: không còn "
        "cập nhật hộ tập trung."
    )
    print(
        " - GV tổ SENT: nút Điều tra mới "
        "không bị khóa bởi số hộ dự kiến."
    )
    print(
        " - Lớp 10: tự suy ra hoàn thành lớp 9 "
        "và mức biết chữ phù hợp."
    )
    print(
        " - Quy tắc XMC >=15 tuổi vẫn GIỮ NGUYÊN."
    )
    print()
    print(
        "Chuẩn hóa:",
        normalization,
    )
    print("Backup:", BACKUP)
    print("Báo cáo:", REPORT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
