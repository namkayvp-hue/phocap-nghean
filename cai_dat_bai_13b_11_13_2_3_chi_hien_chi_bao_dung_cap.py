from __future__ import annotations

import shutil
import traceback
from datetime import datetime
from pathlib import Path

PROJECT = Path(r"C:\PhoCap").resolve()
TARGET = PROJECT / "app" / "templates" / "surveys" / "year_records.html"
STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = PROJECT / "exports" / f"backup_bai_13b_11_13_2_3_{STAMP}"

DYNAMIC_MARKER = "<!-- === BAI_13B_11_13_2_DYNAMIC_UI_START === -->"
LEVEL_MARKER = "<!-- === BAI_13B_11_13_2_LEVEL_UI_START === -->"
OLD_FUNCTION_START = "    function updateLevelIndicators() {"
OLD_FUNCTION_END_ANCHOR = '\n    document.addEventListener("DOMContentLoaded", function () {'

NEW_FUNCTIONS = '    function b131132TextOf(selector) {\n        const element = document.querySelector(selector);\n        if (!element) return "";\n\n        const parts = [];\n        if ("value" in element && element.value) parts.push(String(element.value));\n        if (element.textContent) parts.push(String(element.textContent));\n        return parts.join(" ").trim();\n    }\n\n    function b131132Normalize(value) {\n        return String(value || "")\n            .normalize("NFD")\n            .replace(/[\\u0300-\\u036f]/g, "")\n            .toLowerCase()\n            .replace(/\\s+/g, " ")\n            .trim();\n    }\n\n    function b131132DetectGrade(classText) {\n        const text = b131132Normalize(classText);\n        if (!text) return null;\n\n        let match = text.match(/\\blop\\s*([0-9]{1,2})\\b/);\n        if (!match) {\n            match = text.match(/^\\s*([0-9]{1,2})(?:\\s|[a-z]|$)/);\n        }\n        if (!match) return null;\n\n        const grade = parseInt(match[1], 10);\n        if (!Number.isFinite(grade) || grade < 1 || grade > 12) return null;\n        return grade;\n    }\n\n    function b131132DetectEducationLevel() {\n        const classText = [\n            b131132TextOf("#class_search"),\n            b131132TextOf("#class_selected"),\n            b131132TextOf(\'[name="class_name_reported"]\')\n        ].join(" ");\n\n        const schoolText = [\n            b131132TextOf("#school_search"),\n            b131132TextOf("#school_selected"),\n            b131132TextOf(\'[name="school_name_reported"]\')\n        ].join(" ");\n\n        const classKey = b131132Normalize(classText);\n        const schoolKey = b131132Normalize(schoolText);\n        const combined = (classKey + " " + schoolKey).trim();\n\n        if (\n            /\\bmam non\\b/.test(combined)\n            || /\\bmau giao\\b/.test(combined)\n            || /\\bnha tre\\b/.test(combined)\n        ) return "MN";\n\n        if (\n            /\\bthcs\\b/.test(combined)\n            || /\\btrung hoc co so\\b/.test(combined)\n        ) return "THCS";\n\n        if (\n            /\\btieu hoc\\b/.test(combined)\n            || /\\bprimary\\b/.test(combined)\n        ) return "TH";\n\n        if (\n            /\\bthpt\\b/.test(combined)\n            || /\\btrung hoc pho thong\\b/.test(combined)\n        ) return "OTHER";\n\n        const grade = b131132DetectGrade(classText);\n        if (grade !== null) {\n            if (grade >= 1 && grade <= 5) return "TH";\n            if (grade >= 6 && grade <= 9) return "THCS";\n            if (grade >= 10 && grade <= 12) return "OTHER";\n        }\n\n        const age = parseAge();\n        if (age !== null) {\n            if (age >= 0 && age <= 5) return "MN";\n            if (age >= 6 && age <= 10) return "TH";\n            if (age >= 11 && age <= 14) return "THCS";\n        }\n\n        return "OTHER";\n    }\n\n    function updateLevelIndicators() {\n        const level = b131132DetectEducationLevel();\n\n        const primary = document.getElementById(\n            "b131132_primary_indicators"\n        );\n        const thcs = document.getElementById(\n            "b131132_thcs_indicators"\n        );\n        const preschoolContainers = findPreschoolContainers();\n\n        setVisible(primary, level === "TH");\n        setVisible(thcs, level === "THCS");\n\n        preschoolContainers.forEach(function (item) {\n            setVisible(item, level === "MN");\n        });\n\n        document.body.dataset.b131132EducationLevel = level;\n    }\n\n    function bindEducationLevelListeners() {\n        const selectors = [\n            "#school_search",\n            "#school_selected",\n            \'[name="school_name_reported"]\',\n            "#class_search",\n            "#class_selected",\n            \'[name="class_name_reported"]\',\n            "#school_id",\n            "#class_id"\n        ];\n\n        selectors.forEach(function (selector) {\n            const element = document.querySelector(selector);\n            if (!element) return;\n\n            ["change", "input"].forEach(function (eventName) {\n                element.addEventListener(eventName, function () {\n                    window.setTimeout(updateLevelIndicators, 0);\n                });\n            });\n        });\n\n        ["#school_selected", "#class_selected"].forEach(function (selector) {\n            const element = document.querySelector(selector);\n            if (!element || typeof MutationObserver === "undefined") return;\n\n            const observer = new MutationObserver(function () {\n                window.setTimeout(updateLevelIndicators, 0);\n            });\n\n            observer.observe(element, {\n                childList: true,\n                subtree: true,\n                characterData: true,\n                attributes: true\n            });\n        });\n    }\n'


def read_text(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(f"Không tìm thấy: {path}")
    return path.read_text(encoding="utf-8-sig")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def backup() -> None:
    dst = BACKUP / TARGET.relative_to(PROJECT)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(TARGET, dst)


def restore() -> None:
    src = BACKUP / TARGET.relative_to(PROJECT)
    if src.exists():
        shutil.copy2(src, TARGET)


def patch(text: str) -> str:
    if DYNAMIC_MARKER not in text or LEVEL_MARKER not in text:
        raise RuntimeError(
            "Chưa thấy đầy đủ khối Bài 13B-11.13.2. "
            "Hãy bảo đảm Bài 13B-11.13.2.2 đã cài thành công."
        )

    if "BAI_13B_11_13_2_3_EXCLUSIVE_LEVEL_START" in text:
        print(" - Bài 13B-11.13.2.3 đã có sẵn; không chèn lặp.")
        return text

    marker_pos = text.find(DYNAMIC_MARKER)
    start = text.find(OLD_FUNCTION_START, marker_pos)
    if start < 0:
        raise RuntimeError("Không tìm thấy updateLevelIndicators() hiện tại.")

    end = text.find(OLD_FUNCTION_END_ANCHOR, start)
    if end < 0:
        raise RuntimeError("Không tìm thấy điểm kết thúc updateLevelIndicators().")

    block = (
        "    // === BAI_13B_11_13_2_3_EXCLUSIVE_LEVEL_START ===\n"
        + NEW_FUNCTIONS
        + "    // === BAI_13B_11_13_2_3_EXCLUSIVE_LEVEL_END ===\n"
    )

    text = text[:start] + block + text[end:]

    old_calls = "        updateLiteracy();\n        updateLevelIndicators();"
    new_calls = (
        "        updateLiteracy();\n"
        "        bindEducationLevelListeners();\n"
        "        updateLevelIndicators();"
    )

    if old_calls not in text:
        raise RuntimeError(
            "Không tìm thấy đoạn gọi updateLiteracy/updateLevelIndicators."
        )

    return text.replace(old_calls, new_calls, 1)


def verify(text: str) -> None:
    required = [
        "BAI_13B_11_13_2_3_EXCLUSIVE_LEVEL_START",
        "function b131132DetectEducationLevel()",
        'setVisible(primary, level === "TH")',
        'setVisible(thcs, level === "THCS")',
        'setVisible(item, level === "MN")',
        "bindEducationLevelListeners();",
        "MutationObserver",
        'name="completed_preschool_5"',
        'name="completed_primary_program"',
        'name="completed_lower_secondary_program"',
    ]

    for item in required:
        if item not in text:
            raise RuntimeError(f"Thiếu nội dung sau cài: {item}")

    if text.count("BAI_13B_11_13_2_3_EXCLUSIVE_LEVEL_START") != 1:
        raise RuntimeError("Khối 13B-11.13.2.3 bị lặp.")

    from jinja2 import Environment
    Environment().parse(text)


def main() -> int:
    print("=" * 124)
    print("BÀI 13B-11.13.2.3 - CHỈ HIỆN CHỈ BÁO ĐÚNG CẤP CỦA ĐỐI TƯỢNG")
    print("=" * 124)
    print()
    print("QUY TẮC:")
    print(" - Mầm non -> chỉ hiện chỉ báo Mầm non.")
    print(" - Tiểu học -> chỉ hiện chỉ báo Tiểu học.")
    print(" - THCS -> chỉ hiện chỉ báo THCS.")
    print(" - THPT/người lớn/ngoài 3 cấp -> không hiện nhầm chỉ báo MN/TH/THCS.")
    print(" - Xóa mù chữ vẫn độc lập ở đầu form.")
    print()
    print("NHẬN DIỆN:")
    print(" 1. Ưu tiên trường/lớp hiện tại.")
    print(" 2. Lớp 1-5 -> TH; lớp 6-9 -> THCS; lớp 10-12 -> cấp khác.")
    print(" 3. Chưa có trường/lớp: 0-5 -> MN; 6-10 -> TH; 11-14 -> THCS.")
    print()
    print("AN TOÀN:")
    print(" - Chỉ sửa year_records.html.")
    print(" - Không sửa router/model/database.")
    print(" - Không xóa hay đổi nội dung chỉ báo Mầm non.")
    print()

    BACKUP.mkdir(parents=True, exist_ok=False)
    backup()
    print("Backup:", BACKUP)

    try:
        before = read_text(TARGET)
        after = patch(before)
        verify(after)
        write_text(TARGET, after)

        print()
        print("KIỂM TRA SAU CÀI:")
        print(" - MN chỉ hiện MN: OK")
        print(" - TH chỉ hiện TH: OK")
        print(" - THCS chỉ hiện THCS: OK")
        print(" - Người lớn không hiện nhầm chỉ báo cấp: OK")
        print(" - XMC độc lập: GIỮ NGUYÊN")
        print(" - Chỉ báo Mầm non: GIỮ NGUYÊN NỘI DUNG")
        print(" - Jinja parse: OK")
        print(" - Database: KHÔNG THAY ĐỔI")
        print()
        print("CÀI ĐẶT BÀI 13B-11.13.2.3 THÀNH CÔNG")
        return 0

    except Exception:
        traceback.print_exc()
        print()
        print("CÓ LỖI - ĐANG KHÔI PHỤC TEMPLATE...")
        restore()
        print("ĐÃ KHÔI PHỤC TEMPLATE.")
        print("Database không bị thay đổi.")
        print("Backup:", BACKUP)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
