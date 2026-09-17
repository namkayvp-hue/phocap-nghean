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
BACKUP = EXPORTS / f"backup_bai_13b_12_v2_3_10_{STAMP}"
DB_BACKUP = BACKUP / "phocap.db"
REPORT = EXPORTS / f"bao_cao_cai_bai_13b_12_v2_3_10_{STAMP}.txt"

V239_UI_START = "<!-- === BAI_13B_12_V2_3_9_DERIVED_GRADE_UI_START === -->"
V239_UI_END = "<!-- === BAI_13B_12_V2_3_9_DERIVED_GRADE_UI_END === -->"
V2310_UI_START = "<!-- === BAI_13B_12_V2_3_10_EDUCATION_CONSISTENCY_UI_START === -->"
V2310_BACKEND = "BAI_13B_12_V2_3_10_EDUCATION_CONSISTENCY_BACKEND"

CURRENT_CLASS_END = "        # === BAI_13B_12_V2_3_3_CURRENT_CLASS_SOURCE_END ===\n"

NEW_UI_BLOCK = '<!-- === BAI_13B_12_V2_3_10_EDUCATION_CONSISTENCY_UI_START === -->\n<script>\n(function () {\n    "use strict";\n\n    function toGrade(value) {\n        const raw = String(value == null ? "" : value).trim();\n        if (raw === "") return null;\n        const n = Number(raw);\n        if (!Number.isFinite(n) || n < 0 || n > 12) return null;\n        return n;\n    }\n\n    function normalizedAttainment(grade, current) {\n        const level = String(current || "CHUA_XAC_DINH").trim().toUpperCase();\n\n        if (grade === null) return level;\n        if (grade <= 4) return "CHUA_HOAN_THANH_TIEU_HOC";\n        if (grade <= 8) return "TIEU_HOC";\n        if (grade <= 11) {\n            return level === "TRUNG_CAP" ? "TRUNG_CAP" : "THCS";\n        }\n\n        const allowedAfter12 = new Set([\n            "THPT",\n            "TRUNG_CAP",\n            "CAO_DANG",\n            "DAI_HOC",\n            "SAU_DAI_HOC",\n            "KHAC"\n        ]);\n        return allowedAfter12.has(level) ? level : "THPT";\n    }\n\n    function makeDerivedSelect(select) {\n        if (!select) return;\n        select.disabled = false;\n        select.style.pointerEvents = "none";\n        select.tabIndex = -1;\n        select.setAttribute("aria-readonly", "true");\n        select.title = "Hệ thống tự suy ra từ Lớp cao nhất đã hoàn thành.";\n    }\n\n    function syncEducationConsistency() {\n        const highest = document.getElementById("highest_completed_grade");\n        const level = document.getElementById("education_attainment_level");\n        const g3 = document.getElementById("completed_grade_3");\n        const g5 = document.getElementById("completed_grade_5");\n        if (!highest) return;\n\n        const grade = toGrade(highest.value);\n\n        if (g3) {\n            g3.value = grade === null\n                ? "CHUA_XAC_DINH"\n                : (grade >= 3 ? "CO" : "KHONG");\n            makeDerivedSelect(g3);\n        }\n\n        if (g5) {\n            g5.value = grade === null\n                ? "CHUA_XAC_DINH"\n                : (grade >= 5 ? "CO" : "KHONG");\n            makeDerivedSelect(g5);\n        }\n\n        if (level && grade !== null) {\n            const next = normalizedAttainment(grade, level.value);\n            if (String(level.value || "") !== next) {\n                level.value = next;\n            }\n        }\n    }\n\n    document.addEventListener("DOMContentLoaded", function () {\n        const highest = document.getElementById("highest_completed_grade");\n        const level = document.getElementById("education_attainment_level");\n\n        if (highest) {\n            highest.addEventListener("change", syncEducationConsistency);\n            highest.addEventListener("input", syncEducationConsistency);\n        }\n\n        if (level) {\n            level.addEventListener("change", syncEducationConsistency);\n        }\n\n        syncEducationConsistency();\n        [80, 250, 700].forEach(function (delay) {\n            window.setTimeout(syncEducationConsistency, delay);\n        });\n    });\n})();\n</script>\n<!-- === BAI_13B_12_V2_3_10_EDUCATION_CONSISTENCY_UI_END === -->\n'
BACKEND_BLOCK = '\n        # === BAI_13B_12_V2_3_10_EDUCATION_CONSISTENCY_BACKEND_START ===\n        # Lớp cao nhất đã hoàn thành là nguồn kiểm soát nhất quán cho\n        # trình độ phổ thông. Trình độ nghề/higher education chỉ được\n        # giữ khi lớp phổ thông đã đạt ngưỡng hợp lý.\n        if _b1312v21_grade_value is not None:\n            if _b1312v21_grade_value <= 4:\n                _b1312v21_level_value = (\n                    "CHUA_HOAN_THANH_TIEU_HOC"\n                )\n            elif _b1312v21_grade_value <= 8:\n                _b1312v21_level_value = "TIEU_HOC"\n            elif _b1312v21_grade_value <= 11:\n                if _b1312v21_level_value != "TRUNG_CAP":\n                    _b1312v21_level_value = "THCS"\n            else:\n                _b132310_allowed_after_12 = {\n                    "THPT",\n                    "TRUNG_CAP",\n                    "CAO_DANG",\n                    "DAI_HOC",\n                    "SAU_DAI_HOC",\n                    "KHAC",\n                }\n                if (\n                    _b1312v21_level_value\n                    not in _b132310_allowed_after_12\n                ):\n                    _b1312v21_level_value = "THPT"\n        # === BAI_13B_12_V2_3_10_EDUCATION_CONSISTENCY_BACKEND_END ===\n'

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
        integrity = str(con.execute("PRAGMA integrity_check").fetchone()[0])
        fk_count = len(con.execute("PRAGMA foreign_key_check").fetchall())
        counts = {}
        for table in (
            "survey_forms",
            "survey_people",
            "survey_person_year_records",
        ):
            counts[table] = int(
                con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            )
        return {
            "integrity": integrity,
            "fk_count": fk_count,
            "counts": counts,
        }
    finally:
        con.close()

def inconsistent_rows() -> list[tuple]:
    con = sqlite3.connect(str(DB))
    try:
        return con.execute(
            """
            SELECT
                id,
                survey_person_id,
                school_year_id,
                highest_completed_grade,
                education_attainment_level
            FROM survey_person_year_records
            WHERE highest_completed_grade IS NOT NULL
              AND (
                    (
                        highest_completed_grade BETWEEN 0 AND 4
                        AND COALESCE(education_attainment_level, '') !=
                            'CHUA_HOAN_THANH_TIEU_HOC'
                    )
                 OR (
                        highest_completed_grade BETWEEN 5 AND 8
                        AND COALESCE(education_attainment_level, '') !=
                            'TIEU_HOC'
                    )
                 OR (
                        highest_completed_grade BETWEEN 9 AND 11
                        AND COALESCE(education_attainment_level, '')
                            NOT IN ('THCS', 'TRUNG_CAP')
                    )
                 OR (
                        highest_completed_grade = 12
                        AND COALESCE(education_attainment_level, '')
                            NOT IN (
                                'THPT', 'TRUNG_CAP', 'CAO_DANG',
                                'DAI_HOC', 'SAU_DAI_HOC', 'KHAC'
                            )
                    )
              )
            ORDER BY id
            """
        ).fetchall()
    finally:
        con.close()

def patch_template(source: str) -> str:
    if V2310_UI_START in source:
        return source

    if V239_UI_START not in source or V239_UI_END not in source:
        raise RuntimeError(
            "Không tìm thấy đúng khối V2.3.9 trên year_records.html."
        )

    pattern = re.compile(
        re.escape(V239_UI_START)
        + r".*?"
        + re.escape(V239_UI_END)
        + r"\s*",
        re.S,
    )
    new_source, count = pattern.subn(NEW_UI_BLOCK, source, count=1)
    if count != 1:
        raise RuntimeError(
            f"Số khối V2.3.9 UI tìm được bất thường: {count}"
        )

    if "g3.disabled = true" in new_source or "g5.disabled = true" in new_source:
        raise RuntimeError(
            "Vẫn còn câu lệnh disabled của V2.3.9 trong template."
        )

    return new_source

def patch_backend(source: str) -> str:
    if V2310_BACKEND in source:
        return source

    required = (
        "BAI_13B_12_V2_3_CLASS_TO_ATTAINMENT_START",
        "BAI_13B_12_V2_3_3_CURRENT_CLASS_SOURCE_START",
        "BAI_13B_12_V2_3_3_CURRENT_CLASS_SOURCE_END",
        "BAI_13B_12_V2_3_GRADE_TO_XMC_START",
        "BAI_13B_12_V2_3_9_AUTO_FINISH_HOUSEHOLD_START",
        "record.highest_completed_grade = (",
        "record.education_attainment_level = (",
    )
    for token in required:
        if token not in source:
            raise RuntimeError("Thiếu nền cần thiết: " + token)

    count = source.count(CURRENT_CLASS_END)
    if count != 1:
        raise RuntimeError(
            "Số marker CURRENT_CLASS_SOURCE_END bất thường: "
            + str(count)
        )

    result = source.replace(
        CURRENT_CLASS_END,
        CURRENT_CLASS_END + BACKEND_BLOCK,
        1,
    )
    ast.parse(result)
    return result

def verify_source() -> None:
    s = read_text(SURVEYS)
    t = read_text(YEAR_TEMPLATE)

    for token in (
        "BAI_13B_12_V2_3_10_EDUCATION_CONSISTENCY_BACKEND_START",
        '_b1312v21_level_value = "TIEU_HOC"',
        '_b1312v21_level_value = "THCS"',
        '_b1312v21_level_value = "THPT"',
        "BAI_13B_12_V2_3_GRADE_TO_XMC_START",
        "BAI_13B_12_V2_3_9_AUTO_FINISH_HOUSEHOLD_START",
    ):
        if token not in s:
            raise RuntimeError("Verifier backend thiếu: " + token)

    for token in (
        V2310_UI_START,
        'grade >= 3 ? "CO" : "KHONG"',
        'grade >= 5 ? "CO" : "KHONG"',
        'select.disabled = false',
        'select.style.pointerEvents = "none"',
        'return "CHUA_HOAN_THANH_TIEU_HOC"',
        'return "TIEU_HOC"',
        'return level === "TRUNG_CAP" ? "TRUNG_CAP" : "THCS"',
    ):
        if token not in t:
            raise RuntimeError("Verifier template thiếu: " + token)

    if "g3.disabled = true" in t or "g5.disabled = true" in t:
        raise RuntimeError("Verifier: vẫn còn disabled V2.3.9.")

    ast.parse(s)
    py_compile.compile(str(SURVEYS), doraise=True)
    Environment().parse(t)

def main() -> int:
    print("=" * 118)
    print("BÀI 13B-12 V2.3.10 - ĐỒNG BỘ LỚP CAO NHẤT VÀ TRÌNH ĐỘ HỌC VẤN")
    print("=" * 118)

    for path in (DB, SURVEYS, YEAR_TEMPLATE):
        if not path.exists():
            print("DỪNG AN TOÀN: thiếu", path)
            return 2

    before = db_state()
    before_bad = inconsistent_rows()

    print("integrity_check:", before["integrity"])
    print("foreign_key_check:", before["fk_count"], "lỗi")
    print("Bản ghi trình độ đang mâu thuẫn:", len(before_bad))

    if before["integrity"].lower() != "ok" or before["fk_count"] != 0:
        print("DỪNG: database chưa đạt kiểm tra an toàn.")
        return 3

    old_s = read_text(SURVEYS)
    old_t = read_text(YEAR_TEMPLATE)

    if (
        "BAI_13B_12_V2_3_10_EDUCATION_CONSISTENCY_BACKEND_START"
        in old_s
        and V2310_UI_START in old_t
    ):
        print("V2.3.10 đã cài. Không cài lặp.")
        return 0

    try:
        new_s = patch_backend(old_s)
        new_t = patch_template(old_t)
        ast.parse(new_s)
        Environment().parse(new_t)
    except Exception as exc:
        print()
        print("DỪNG AN TOÀN TRƯỚC KHI GHI SOURCE:")
        print(type(exc).__name__ + ":", exc)
        return 4

    EXPORTS.mkdir(parents=True, exist_ok=True)
    BACKUP.mkdir(parents=True, exist_ok=False)
    backup_file(SURVEYS)
    backup_file(YEAR_TEMPLATE)
    backup_db()
    print("Backup:", BACKUP)

    try:
        write_text(SURVEYS, new_s)
        write_text(YEAR_TEMPLATE, new_t)
        verify_source()

        after = db_state()
        after_bad = inconsistent_rows()

        if after["integrity"].lower() != "ok":
            raise RuntimeError("integrity_check không đạt sau cài.")
        if after["fk_count"] != 0:
            raise RuntimeError("foreign_key_check có lỗi sau cài.")
        if after["counts"] != before["counts"]:
            raise RuntimeError(
                "Số lượng bản ghi database thay đổi ngoài dự kiến."
            )
        if after_bad != before_bad:
            raise RuntimeError(
                "Bộ cài đã làm thay đổi dữ liệu trình độ; "
                "V2.3.10 không được tự sửa dữ liệu hiện có."
            )

        for cache in APP.rglob("__pycache__"):
            if cache.is_dir():
                shutil.rmtree(cache, ignore_errors=True)

    except Exception as exc:
        print()
        print("CÓ LỖI - ĐANG ROLLBACK SOURCE + DATABASE...")
        print(type(exc).__name__ + ":", exc)
        restore_file(SURVEYS)
        restore_file(YEAR_TEMPLATE)
        restore_db()
        print("ĐÃ KHÔI PHỤC.")
        return 9

    report_lines = [
        "=" * 118,
        "BÁO CÁO CÀI BÀI 13B-12 V2.3.10",
        "=" * 118,
        f"Thời gian: {datetime.now():%d/%m/%Y %H:%M:%S}",
        "",
        "ĐÃ SỬA:",
        "1. Hoàn thành lớp 3/lớp 5 vẫn là dữ liệu suy ra nhưng select không còn disabled;",
        "   vì vậy giá trị vẫn được gửi khi POST.",
        "2. Backend chuẩn hóa trình độ học vấn theo Lớp cao nhất đã hoàn thành.",
        "3. JavaScript đồng bộ ngay trên màn hình để không còn hiển thị tổ hợp mâu thuẫn.",
        "4. Giữ nguyên quy tắc XMC cũ và V2.3.9 hoàn thành hộ.",
        "",
        "QUY TẮC NHẤT QUÁN:",
        "- Lớp 0-4  -> Chưa hoàn thành chương trình Tiểu học.",
        "- Lớp 5-8  -> Hoàn thành Tiểu học.",
        "- Lớp 9-11 -> Tốt nghiệp THCS; cho phép Trung cấp nếu đã xác nhận.",
        "- Lớp 12   -> tối thiểu THPT; cho phép Trung cấp/Cao đẳng/Đại học/Sau ĐH/Khác.",
        "",
        "LƯU Ý:",
        "- Bộ cài KHÔNG tự sửa dữ liệu đang có.",
        "- Bản ghi mâu thuẫn cũ sẽ được chuẩn hóa khi người dùng mở và bấm Lưu lại.",
        f"- Số bản ghi mâu thuẫn hiện có lúc cài: {len(before_bad)}.",
        "",
        f"integrity_check: {after['integrity']}",
        f"foreign_key_check: {after['fk_count']} lỗi",
        f"Backup: {BACKUP}",
    ]

    if before_bad:
        report_lines.append("")
        report_lines.append("CÁC BẢN GHI MÂU THUẪN ĐANG CÓ:")
        for row in before_bad[:100]:
            report_lines.append(
                " - id=%s | person=%s | year=%s | grade=%s | level=%s"
                % row
            )

    REPORT.write_text(
        "\n".join(report_lines) + "\n",
        encoding="utf-8-sig",
    )

    print()
    print("=" * 118)
    print("CÀI ĐẶT THÀNH CÔNG BÀI 13B-12 V2.3.10")
    print("=" * 118)
    print(" - Đã khóa mâu thuẫn Lớp cao nhất ↔ Trình độ học vấn ở UI + backend.")
    print(" - Hoàn thành lớp 3/lớp 5 vẫn tự suy và vẫn POST.")
    print(" - Không tự sửa dữ liệu hiện có.")
    print("Báo cáo:", REPORT)
    print("Backup:", BACKUP)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
