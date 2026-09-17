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
BACKUP = EXPORTS / f"backup_bai_13b_12_v2_3_11_{STAMP}"
DB_BACKUP = BACKUP / "phocap.db"
REPORT = EXPORTS / f"bao_cao_cai_bai_13b_12_v2_3_11_{STAMP}.txt"

V2310_UI_START = "<!-- === BAI_13B_12_V2_3_10_EDUCATION_CONSISTENCY_UI_START === -->"
V2310_UI_END = "<!-- === BAI_13B_12_V2_3_10_EDUCATION_CONSISTENCY_UI_END === -->"
V2311_UI_START = "<!-- === BAI_13B_12_V2_3_11_XMC_EDITABLE_CONSISTENCY_UI_START === -->"

V2310_BACKEND_END = "        # === BAI_13B_12_V2_3_10_EDUCATION_CONSISTENCY_BACKEND_END ===\n"
V2311_BACKEND = "BAI_13B_12_V2_3_11_XMC_CONSISTENCY_VALIDATE"

NEW_UI_BLOCK = '<!-- === BAI_13B_12_V2_3_11_XMC_EDITABLE_CONSISTENCY_UI_START === -->\n<script>\n(function () {\n    "use strict";\n\n    function toGrade(value) {\n        const raw = String(value == null ? "" : value).trim();\n        if (raw === "") return null;\n        const n = Number(raw);\n        if (!Number.isFinite(n) || n < 0 || n > 12) return null;\n        return n;\n    }\n\n    function normalizedAttainment(grade, current) {\n        const level = String(current || "CHUA_XAC_DINH").trim().toUpperCase();\n\n        if (grade === null) return level;\n        if (grade <= 4) return "CHUA_HOAN_THANH_TIEU_HOC";\n        if (grade <= 8) return "TIEU_HOC";\n        if (grade <= 11) {\n            return level === "TRUNG_CAP" ? "TRUNG_CAP" : "THCS";\n        }\n\n        const allowedAfter12 = new Set([\n            "THPT",\n            "TRUNG_CAP",\n            "CAO_DANG",\n            "DAI_HOC",\n            "SAU_DAI_HOC",\n            "KHAC"\n        ]);\n        return allowedAfter12.has(level) ? level : "THPT";\n    }\n\n    function unlockXmcSelect(select) {\n        if (!select) return;\n        select.disabled = false;\n        select.style.pointerEvents = "";\n        select.tabIndex = 0;\n        select.removeAttribute("aria-readonly");\n        select.removeAttribute("aria-disabled");\n        select.title = "Được phép chọn theo kết quả điều tra thực tế; hệ thống sẽ kiểm tra tính nhất quán khi lưu.";\n    }\n\n    function expectedFlag(grade, threshold) {\n        if (grade === null) return null;\n        return grade >= threshold ? "CO" : "KHONG";\n    }\n\n    function syncAttainmentAndSuggestXmc(forceXmc) {\n        const highest = document.getElementById("highest_completed_grade");\n        const level = document.getElementById("education_attainment_level");\n        const g3 = document.getElementById("completed_grade_3");\n        const g5 = document.getElementById("completed_grade_5");\n\n        if (!highest) return;\n\n        unlockXmcSelect(g3);\n        unlockXmcSelect(g5);\n\n        const grade = toGrade(highest.value);\n\n        if (level && grade !== null) {\n            const next = normalizedAttainment(grade, level.value);\n            if (String(level.value || "") !== next) {\n                level.value = next;\n            }\n        }\n\n        if (grade === null) return;\n\n        const expected3 = expectedFlag(grade, 3);\n        const expected5 = expectedFlag(grade, 5);\n\n        if (g3) {\n            const current3 = String(g3.value || "").trim().toUpperCase();\n            if (\n                forceXmc\n                || current3 === ""\n                || current3 === "CHUA_XAC_DINH"\n            ) {\n                g3.value = expected3;\n            }\n        }\n\n        if (g5) {\n            const current5 = String(g5.value || "").trim().toUpperCase();\n            if (\n                forceXmc\n                || current5 === ""\n                || current5 === "CHUA_XAC_DINH"\n            ) {\n                g5.value = expected5;\n            }\n        }\n    }\n\n    document.addEventListener("DOMContentLoaded", function () {\n        const highest = document.getElementById("highest_completed_grade");\n        const level = document.getElementById("education_attainment_level");\n        const g3 = document.getElementById("completed_grade_3");\n        const g5 = document.getElementById("completed_grade_5");\n\n        unlockXmcSelect(g3);\n        unlockXmcSelect(g5);\n\n        if (highest) {\n            highest.addEventListener("change", function () {\n                syncAttainmentAndSuggestXmc(true);\n            });\n            highest.addEventListener("input", function () {\n                syncAttainmentAndSuggestXmc(true);\n            });\n        }\n\n        if (level) {\n            level.addEventListener("change", function () {\n                syncAttainmentAndSuggestXmc(false);\n            });\n        }\n\n        syncAttainmentAndSuggestXmc(false);\n\n        [80, 250, 700].forEach(function (delay) {\n            window.setTimeout(function () {\n                unlockXmcSelect(g3);\n                unlockXmcSelect(g5);\n                syncAttainmentAndSuggestXmc(false);\n            }, delay);\n        });\n    });\n})();\n</script>\n<!-- === BAI_13B_12_V2_3_11_XMC_EDITABLE_CONSISTENCY_UI_END === -->\n'
BACKEND_BLOCK = '\n    # === BAI_13B_12_V2_3_11_XMC_CONSISTENCY_VALIDATE_START ===\n    # completed_grade_3/5 vẫn là chỉ báo XMC theo quy tắc cũ và được phép\n    # người điều tra lựa chọn. Tuy nhiên khi đã khai báo Lớp cao nhất đã\n    # hoàn thành thì không cho lưu tổ hợp mâu thuẫn.\n    def _b132311_parse_xmc_bool(raw_value):\n        _raw = str(raw_value or "").strip().upper()\n        if _raw in {"CO", "1", "TRUE", "YES"}:\n            return True\n        if _raw in {"KHONG", "0", "FALSE", "NO"}:\n            return False\n        return None\n\n    _b132311_g3 = _b132311_parse_xmc_bool(completed_grade_3)\n    _b132311_g5 = _b132311_parse_xmc_bool(completed_grade_5)\n\n    if _b1312v21_grade_value is not None:\n        _b132311_expected_g3 = (_b1312v21_grade_value >= 3)\n        _b132311_expected_g5 = (_b1312v21_grade_value >= 5)\n\n        if (\n            _b132311_g3 is not None\n            and _b132311_g3 != _b132311_expected_g3\n        ):\n            errors.append(\n                "Mâu thuẫn dữ liệu Xóa mù chữ: "\n                "Hoàn thành lớp 3 không phù hợp với "\n                "Lớp cao nhất đã hoàn thành."\n            )\n\n        if (\n            _b132311_g5 is not None\n            and _b132311_g5 != _b132311_expected_g5\n        ):\n            errors.append(\n                "Mâu thuẫn dữ liệu Xóa mù chữ: "\n                "Hoàn thành lớp 5 không phù hợp với "\n                "Lớp cao nhất đã hoàn thành."\n            )\n\n    if _b132311_g5 is True and _b132311_g3 is False:\n        errors.append(\n            "Mâu thuẫn dữ liệu Xóa mù chữ: "\n            "đã hoàn thành lớp 5 thì phải hoàn thành lớp 3."\n        )\n    # === BAI_13B_12_V2_3_11_XMC_CONSISTENCY_VALIDATE_END ===\n'

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

def patch_template(source: str) -> str:
    if V2311_UI_START in source:
        return source

    if V2310_UI_START not in source or V2310_UI_END not in source:
        raise RuntimeError(
            "Không tìm thấy đúng khối UI V2.3.10 để nâng cấp."
        )

    pattern = re.compile(
        re.escape(V2310_UI_START)
        + r".*?"
        + re.escape(V2310_UI_END)
        + r"\s*",
        re.S,
    )

    result, count = pattern.subn(NEW_UI_BLOCK, source, count=1)
    if count != 1:
        raise RuntimeError(
            f"Số khối UI V2.3.10 tìm được bất thường: {count}"
        )

    return result

def patch_backend(source: str) -> str:
    if V2311_BACKEND in source:
        return source

    required = (
        "BAI_13B_12_V2_3_10_EDUCATION_CONSISTENCY_BACKEND_START",
        "BAI_13B_12_V2_3_10_EDUCATION_CONSISTENCY_BACKEND_END",
        "BAI_13B_12_V2_3_GRADE_TO_XMC_START",
        "BAI_13B_12_V2_3_9_AUTO_FINISH_HOUSEHOLD_START",
    )
    for token in required:
        if token not in source:
            raise RuntimeError("Thiếu nền V2.3.10/V2.3.9: " + token)

    count = source.count(V2310_BACKEND_END)
    if count != 1:
        raise RuntimeError(
            "Số marker backend V2.3.10 END bất thường: "
            + str(count)
        )

    result = source.replace(
        V2310_BACKEND_END,
        V2310_BACKEND_END + BACKEND_BLOCK,
        1,
    )

    ast.parse(result)
    return result

def verify_source() -> None:
    s = read_text(SURVEYS)
    t = read_text(YEAR_TEMPLATE)

    for token in (
        "BAI_13B_12_V2_3_11_XMC_CONSISTENCY_VALIDATE_START",
        "_b132311_parse_xmc_bool",
        "Mâu thuẫn dữ liệu Xóa mù chữ",
        "BAI_13B_12_V2_3_GRADE_TO_XMC_START",
        "BAI_13B_12_V2_3_9_AUTO_FINISH_HOUSEHOLD_START",
    ):
        if token not in s:
            raise RuntimeError("Verifier backend thiếu: " + token)

    for token in (
        V2311_UI_START,
        "unlockXmcSelect",
        "select.disabled = false",
        'select.style.pointerEvents = ""',
        "syncAttainmentAndSuggestXmc",
    ):
        if token not in t:
            raise RuntimeError("Verifier UI thiếu: " + token)

    if 'select.style.pointerEvents = "none"' in t:
        raise RuntimeError(
            "Vẫn còn khóa pointer-events của V2.3.10 trong khối mới."
        )

    ast.parse(s)
    py_compile.compile(str(SURVEYS), doraise=True)
    Environment().parse(t)

def main() -> int:
    print("=" * 118)
    print("BÀI 13B-12 V2.3.11 - MỞ LẠI CHỈ BÁO XMC + KIỂM TRA MÂU THUẪN")
    print("=" * 118)

    for path in (DB, SURVEYS, YEAR_TEMPLATE):
        if not path.exists():
            print("DỪNG AN TOÀN: thiếu", path)
            return 2

    before = db_state()
    print("integrity_check:", before["integrity"])
    print("foreign_key_check:", before["fk_count"], "lỗi")

    if before["integrity"].lower() != "ok" or before["fk_count"] != 0:
        print("DỪNG: database chưa đạt kiểm tra an toàn.")
        return 3

    old_s = read_text(SURVEYS)
    old_t = read_text(YEAR_TEMPLATE)

    if V2311_BACKEND in old_s and V2311_UI_START in old_t:
        print("V2.3.11 đã cài. Không cài lặp.")
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
        if after["integrity"].lower() != "ok":
            raise RuntimeError("integrity_check không đạt sau cài.")
        if after["fk_count"] != 0:
            raise RuntimeError("foreign_key_check có lỗi sau cài.")
        if after["counts"] != before["counts"]:
            raise RuntimeError(
                "Database đã thay đổi số bản ghi ngoài dự kiến."
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

    lines = [
        "=" * 118,
        "BÁO CÁO CÀI BÀI 13B-12 V2.3.11",
        "=" * 118,
        f"Thời gian: {datetime.now():%d/%m/%Y %H:%M:%S}",
        "",
        "ĐÃ SỬA:",
        "1. Mở lại quyền lựa chọn Hoàn thành lớp 3 / Hoàn thành lớp 5.",
        "2. Không còn disabled/pointer-events:none đối với hai chỉ báo XMC.",
        "3. Khi thay đổi Lớp cao nhất, hệ thống chỉ gợi ý lại Có/Không.",
        "4. Khi lưu, backend chặn tổ hợp mâu thuẫn.",
        "5. Giữ nguyên cách suy ra Tình trạng Xóa mù chữ hiện có.",
        "6. Giữ nguyên V2.3.10 đồng bộ trình độ và V2.3.9 hoàn thành hộ.",
        "",
        "VÍ DỤ KIỂM TRA:",
        "- Lớp cao nhất 2: Lớp 3 = Không, Lớp 5 = Không.",
        "- Lớp cao nhất 3 hoặc 4: Lớp 3 = Có, Lớp 5 = Không.",
        "- Lớp cao nhất >=5: Lớp 3 = Có, Lớp 5 = Có.",
        "- Nếu chọn trái quy tắc, hệ thống báo mâu thuẫn và không lưu.",
        "",
        f"integrity_check: {after['integrity']}",
        f"foreign_key_check: {after['fk_count']} lỗi",
        f"Backup: {BACKUP}",
    ]

    REPORT.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8-sig",
    )

    print()
    print("=" * 118)
    print("CÀI ĐẶT THÀNH CÔNG BÀI 13B-12 V2.3.11")
    print("=" * 118)
    print(" - Hoàn thành lớp 3/lớp 5: ĐÃ MỞ LẠI CHO PHÉP CHỌN.")
    print(" - Backend vẫn chặn dữ liệu XMC mâu thuẫn.")
    print(" - Không sửa dữ liệu hiện có.")
    print("Báo cáo:", REPORT)
    print("Backup:", BACKUP)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
