from __future__ import annotations

import os
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

PROJECT = Path(os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")).resolve()
APP = PROJECT / "app"
EXPORTS = PROJECT / "exports"
DB = PROJECT / "data" / "phocap.db"
TEMPLATE = APP / "templates" / "surveys" / "year_records.html"
BUILDERS = APP / "pcgd_xmc_report_builders_v1.py"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = EXPORTS / f"backup_bai_13b_11_15_2_4_7_1b_1_{STAMP}"
REPORT = EXPORTS / f"bao_cao_bai_13b_11_15_2_4_7_1b_1_{STAMP}.txt"

SCRIPT_START = "<!-- === BAI_13B_11_15_2_4_7_1B_DERIVED_STATUS_SCRIPT_START === -->"
SCRIPT_END = "<!-- === BAI_13B_11_15_2_4_7_1B_DERIVED_STATUS_SCRIPT_END === -->"
UI_MARKER = "<!-- === BAI_13B_11_15_2_4_7_1B_DERIVED_STATUS_UI_START === -->"
REPORT_MARKER = "# === BAI_13B_11_15_2_4_7_1B_REPORT_SOURCE_START ==="

NEW_SCRIPT = '<!-- === BAI_13B_11_15_2_4_7_1B_DERIVED_STATUS_SCRIPT_START === -->\n<script>\n(function () {\n    "use strict";\n\n    function deriveXmcStatusText() {\n        const g3 = document.getElementById("completed_grade_3");\n        const g5 = document.getElementById("completed_grade_5");\n        const output = document.getElementById("b1471b_literacy_status_text");\n\n        if (!g3 || !g5 || !output) {\n            return;\n        }\n\n        const v3 = String(g3.value || "").toUpperCase();\n        const v5 = String(g5.value || "").toUpperCase();\n\n        let text = "Chưa đủ dữ liệu xác định";\n\n        if (v3 === "KHONG" && v5 === "KHONG") {\n            text = "Mù chữ mức độ 1 và mức độ 2";\n        } else if (v3 === "CO" && v5 === "KHONG") {\n            text = "Biết chữ mức độ 1; Mù chữ mức độ 2";\n        } else if (v3 === "CO" && v5 === "CO") {\n            text = "Biết chữ mức độ 1 và mức độ 2";\n        } else if (v3 === "KHONG" && v5 === "CO") {\n            text = "Dữ liệu cần rà soát: đã hoàn thành lớp 5 nhưng chưa hoàn thành lớp 3";\n        }\n\n        output.textContent = text;\n    }\n\n    document.addEventListener("DOMContentLoaded", function () {\n        const g3 = document.getElementById("completed_grade_3");\n        const g5 = document.getElementById("completed_grade_5");\n\n        if (g3) {\n            g3.addEventListener("change", deriveXmcStatusText);\n        }\n\n        if (g5) {\n            g5.addEventListener("change", deriveXmcStatusText);\n        }\n\n        deriveXmcStatusText();\n        window.setTimeout(deriveXmcStatusText, 120);\n        window.setTimeout(deriveXmcStatusText, 450);\n    });\n})();\n</script>\n<!-- === BAI_13B_11_15_2_4_7_1B_DERIVED_STATUS_SCRIPT_END === -->'


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
                conn.execute(
                    "SELECT COUNT(*) FROM survey_person_year_records"
                ).fetchone()[0]
            ),
            "g3_true": int(
                conn.execute(
                    "SELECT COUNT(*) FROM survey_person_year_records "
                    "WHERE completed_grade_3 = 1"
                ).fetchone()[0]
            ),
            "g3_false": int(
                conn.execute(
                    "SELECT COUNT(*) FROM survey_person_year_records "
                    "WHERE completed_grade_3 = 0"
                ).fetchone()[0]
            ),
            "g5_true": int(
                conn.execute(
                    "SELECT COUNT(*) FROM survey_person_year_records "
                    "WHERE completed_grade_5 = 1"
                ).fetchone()[0]
            ),
            "g5_false": int(
                conn.execute(
                    "SELECT COUNT(*) FROM survey_person_year_records "
                    "WHERE completed_grade_5 = 0"
                ).fetchone()[0]
            ),
        }
    finally:
        conn.close()


def patch_template(source: str) -> str:
    if UI_MARKER not in source:
        raise RuntimeError("Chưa thấy giao diện Bài 4.7.1B.")

    start = source.find(SCRIPT_START)
    end = source.find(SCRIPT_END, start)

    if start < 0 or end < 0:
        raise RuntimeError(
            "Không tìm thấy đúng script suy ra XMC của Bài 4.7.1B."
        )

    end += len(SCRIPT_END)

    return source[:start] + NEW_SCRIPT + source[end:]


def verify_template(source: str) -> None:
    required = (
        UI_MARKER,
        SCRIPT_START,
        SCRIPT_END,
        "Mù chữ mức độ 1 và mức độ 2",
        "Biết chữ mức độ 1; Mù chữ mức độ 2",
        "Biết chữ mức độ 1 và mức độ 2",
        "đã hoàn thành lớp 5 nhưng chưa hoàn thành lớp 3",
    )

    for token in required:
        if token not in source:
            raise RuntimeError("Verifier template thiếu: " + token)

    block = source[
        source.find(SCRIPT_START):
        source.find(SCRIPT_END) + len(SCRIPT_END)
    ]

    if "MutationObserver" in block:
        raise RuntimeError("Không cho phép MutationObserver.")

    from jinja2 import Environment
    Environment().parse(source)


def verify_reports(source: str) -> None:
    if REPORT_MARKER not in source:
        raise RuntimeError("Chưa thấy nguồn báo cáo Bài 4.7.1B.")

    required = (
        'grade3 is False',
        'grade3 is True',
        'grade5 is False',
        'grade5 is True',
        'item["mc1_total"] += 1',
        'item["bc1_total"] += 1',
        'item["mc2_total"] += 1',
        'item["bc2_total"] += 1',
    )

    for token in required:
        if token not in source:
            raise RuntimeError(
                "Nguồn báo cáo chưa đúng quy tắc chốt. Thiếu: " + token
            )


def main() -> None:
    print("=" * 140)
    print(
        "BÀI 13B-11.15.2.4.7.1B.1 - "
        "CHUẨN HÓA HIỂN THỊ MỨC ĐỘ XMC"
    )
    print("=" * 140)
    print()
    print("QUY TẮC CHỐT:")
    print(" - Lớp 3 Không + lớp 5 Không => Mù chữ mức 1 và mức 2.")
    print(" - Lớp 3 Có + lớp 5 Không => Biết chữ mức 1 + Mù chữ mức 2.")
    print(" - Lớp 3 Có + lớp 5 Có => Biết chữ mức 1 và mức 2.")
    print(" - Lớp 3 Không + lớp 5 Có => dữ liệu mâu thuẫn, cần rà soát.")
    print()
    print("Bài này chỉ sửa cách HIỂN THỊ; không sửa DB/công thức/menu/route.")
    print()

    old_template = read_text(TEMPLATE)
    builders = read_text(BUILDERS)

    verify_reports(builders)

    new_template = patch_template(old_template)
    verify_template(new_template)

    before = db_state()

    if before.get("exists"):
        if before.get("integrity") != "ok":
            raise RuntimeError("Database integrity_check != ok trước cài.")
        if before.get("fk_count") != 0:
            raise RuntimeError("Database có lỗi foreign key trước cài.")

    EXPORTS.mkdir(parents=True, exist_ok=True)
    BACKUP.mkdir(parents=True, exist_ok=False)
    shutil.copy2(TEMPLATE, BACKUP / TEMPLATE.name)

    try:
        write_text(TEMPLATE, new_template)
        verify_template(read_text(TEMPLATE))

        after = db_state()
        if before != after:
            raise RuntimeError("Database thay đổi ngoài dự kiến.")

    except Exception:
        shutil.copy2(BACKUP / TEMPLATE.name, TEMPLATE)
        raise

    REPORT.write_text(
        "\n".join(
            (
                "=" * 140,
                "BÀI 13B-11.15.2.4.7.1B.1 - KẾT QUẢ",
                "=" * 140,
                "",
                "ĐÃ CHUẨN HÓA HIỂN THỊ:",
                " - Không/Không -> Mù chữ mức độ 1 và mức độ 2.",
                " - Có/Không -> Biết chữ mức độ 1; Mù chữ mức độ 2.",
                " - Có/Có -> Biết chữ mức độ 1 và mức độ 2.",
                " - Không/Có -> Dữ liệu cần rà soát.",
                "",
                "BÁO CÁO:",
                " - Giữ nguyên logic độc lập grade3/grade5 của 4.7.1B.",
                "",
                "AN TOÀN:",
                " - Database không thay đổi.",
                " - Công thức báo cáo không thay đổi.",
                " - Menu/route không thay đổi.",
                " - Không MutationObserver.",
                f" - Backup: {BACKUP}",
            )
        ),
        encoding="utf-8",
    )

    print("KIỂM TRA:")
    print(" - Jinja parse: OK")
    print(" - Logic report 4.7.1B: OK")
    print(" - Không MutationObserver: OK")
    print(" - Database invariant: OK")
    print()
    print("Backup:", BACKUP)
    print("Báo cáo:", REPORT)
    print()
    print("=" * 140)
    print("BÀI 13B-11.15.2.4.7.1B.1 THÀNH CÔNG")
    print("=" * 140)


if __name__ == "__main__":
    main()
