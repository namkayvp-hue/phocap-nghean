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
BACKUP = EXPORTS / f"backup_bai_13b_12_v2_3_1_{STAMP}"
DB_BACKUP = BACKUP / "phocap.db"
REPORT = EXPORTS / f"bao_cao_cai_bai_13b_12_v2_3_1_{STAMP}.txt"

OLD_PY = r"""    _b1323_current_grade = None
    _b1323_class_match = re.search(
        r"(?i)\bl[oớ]p\s*(1[0-2]|[1-9])\b",
        str(_b1323_current_class_text or ""),
    )
    if _b1323_class_match:
        _b1323_current_grade = int(
            _b1323_class_match.group(1)
        )
"""

NEW_PY = r"""    # === BAI_13B_12_V2_3_1_GRADE_PARSER_START ===
    _b1323_current_grade = None
    _b13231_class_text = str(
        _b1323_current_class_text or ""
    ).strip()
    _b13231_class_fold = _b13231_class_text.casefold()

    # Không nhầm "5 tuổi" của Mầm non thành lớp 5.
    if (
        "tuổi" not in _b13231_class_fold
        and "tuoi" not in _b13231_class_fold
    ):
        _b1323_class_match = re.search(
            r"(?i)\b(?:lớp|lop|khối|khoi)\s*(1[0-2]|[1-9])\b",
            _b13231_class_text,
        )
        if _b1323_class_match is None:
            _b1323_class_match = re.match(
                r"^\s*(1[0-2]|[1-9])"
                r"(?:\s*[A-Za-z]\d*)?\s*$",
                _b13231_class_text,
            )

        if _b1323_class_match:
            _b1323_current_grade = int(
                _b1323_class_match.group(1)
            )
    # === BAI_13B_12_V2_3_1_GRADE_PARSER_END ===
"""

OLD_JS = r"""    function parseGrade(text) {
        const match = String(text || "").match(/l[ớo]p\s*(1[0-2]|[1-9])\b/i);
        return match ? Number(match[1]) : null;
    }
"""

NEW_JS = r"""    function parseGrade(text) {
        const raw = String(text || "").trim();
        const folded = raw.toLocaleLowerCase("vi-VN");

        if (folded.includes("tuổi") || folded.includes("tuoi")) {
            return null;
        }

        let match = raw.match(
            /\b(?:lớp|lop|khối|khoi)\s*(1[0-2]|[1-9])\b/i
        );

        if (!match) {
            match = raw.match(
                /^\s*(1[0-2]|[1-9])(?:\s*[A-Za-z]\d*)?\s*$/
            );
        }

        return match ? Number(match[1]) : null;
    }
"""


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
            "year_records": int(
                con.execute(
                    "SELECT COUNT(*) FROM survey_person_year_records"
                ).fetchone()[0]
            ),
        }
    finally:
        con.close()


def parse_grade(text_value) -> int | None:
    raw = str(text_value or "").strip()
    folded = raw.casefold()

    if "tuổi" in folded or "tuoi" in folded:
        return None

    match = re.search(
        r"(?i)\b(?:lớp|lop|khối|khoi)\s*(1[0-2]|[1-9])\b",
        raw,
    )
    if match is None:
        match = re.match(
            r"^\s*(1[0-2]|[1-9])"
            r"(?:\s*[A-Za-z]\d*)?\s*$",
            raw,
        )

    return int(match.group(1)) if match else None


def normalize_existing_records() -> dict:
    con = sqlite3.connect(str(DB))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")

    result = {
        "checked": 0,
        "class_detected": 0,
        "highest_grade_filled": 0,
        "attainment_filled": 0,
        "xmc_grade_normalized": 0,
        "records_updated": 0,
    }

    try:
        rows = con.execute(
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

        for row in rows:
            result["checked"] += 1

            learning = str(
                row["learning_status"] or ""
            ).strip().upper()

            current_grade = parse_grade(
                row["class_name"] or row["class_name_reported"]
            )
            if current_grade is not None:
                result["class_detected"] += 1

            highest = row["highest_completed_grade"]
            level = str(
                row["education_attainment_level"]
                or "CHUA_XAC_DINH"
            ).strip().upper()

            g3 = row["completed_grade_3"]
            g5 = row["completed_grade_5"]
            literacy = str(
                row["literacy_status"] or "CHUA_XAC_DINH"
            ).strip().upper()

            changed = False

            if (
                learning == "DANG_HOC"
                and current_grade is not None
                and highest is None
            ):
                highest = max(0, current_grade - 1)
                result["highest_grade_filled"] += 1
                changed = True

            if (
                learning == "DANG_HOC"
                and current_grade is not None
                and level == "CHUA_XAC_DINH"
            ):
                if current_grade >= 10:
                    level = "THCS"
                elif current_grade >= 6:
                    level = "TIEU_HOC"
                elif current_grade >= 1:
                    level = "CHUA_HOAN_THANH_TIEU_HOC"

                result["attainment_filled"] += 1
                changed = True

            if (
                row["is_literacy_target"] == 1
                and highest is not None
            ):
                desired_g3 = 1 if int(highest) >= 3 else 0
                desired_g5 = 1 if int(highest) >= 5 else 0
                desired_status = (
                    "KHONG_THUOC_DIEN"
                    if desired_g3 == 1 and desired_g5 == 1
                    else "THEO_DOI_XMC"
                )

                if (
                    g3 != desired_g3
                    or g5 != desired_g5
                    or literacy != desired_status
                ):
                    g3 = desired_g3
                    g5 = desired_g5
                    literacy = desired_status
                    result["xmc_grade_normalized"] += 1
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
                result["records_updated"] += 1

        con.commit()
        return result

    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def main() -> int:
    print("=" * 112)
    print(
        "BÀI 13B-12 V2.3.1 - SỬA NHẬN DẠNG LỚP "
        "10/7/10A1 VÀ TỰ SUY RA XMC"
    )
    print("=" * 112)

    for path in (DB, SURVEYS, YEAR_TEMPLATE):
        if not path.exists():
            print("DỪNG AN TOÀN: thiếu", path)
            return 2

    before = db_state()
    print("integrity_check:", before["integrity"])
    print("foreign_key_check:", before["fk_count"], "lỗi")

    if (
        before["integrity"].lower() != "ok"
        or before["fk_count"] != 0
    ):
        print("DỪNG: Database chưa đạt kiểm tra.")
        return 3

    surveys = read_text(SURVEYS)
    template = read_text(YEAR_TEMPLATE)

    for token in (
        "BAI_13B_12_V2_3_CLASS_TO_ATTAINMENT_START",
        "BAI_13B_12_V2_3_GRADE_TO_XMC_START",
        "BAI_13B_11_15_2_4_7_1A_FORCE_XMC_AGE15_START",
        "BAI_13B_11_15_2_4_7_1B_DERIVE_LITERACY_STATUS_START",
    ):
        if token not in surveys:
            print("DỪNG AN TOÀN: thiếu nền", token)
            return 4

    if "BAI_13B_12_V2_3_1_GRADE_PARSER_START" in surveys:
        print("V2.3.1 đã có trong source. Không cài lặp.")
        return 0

    if OLD_PY not in surveys:
        print(
            "DỪNG AN TOÀN: không tìm thấy parser Python V2.3 "
            "đúng bản dự kiến."
        )
        return 5

    if OLD_JS not in template:
        print(
            "DỪNG AN TOÀN: không tìm thấy parser JavaScript V2.3 "
            "đúng bản dự kiến."
        )
        return 6

    new_surveys = surveys.replace(OLD_PY, NEW_PY, 1)
    new_template = template.replace(OLD_JS, NEW_JS, 1)

    try:
        ast.parse(new_surveys)
        Environment().parse(new_template)
    except Exception as exc:
        print("DỪNG TRƯỚC KHI GHI FILE:", type(exc).__name__, exc)
        return 7

    EXPORTS.mkdir(parents=True, exist_ok=True)
    BACKUP.mkdir(parents=True, exist_ok=False)

    backup_file(SURVEYS)
    backup_file(YEAR_TEMPLATE)
    backup_db()

    print("Backup:", BACKUP)

    try:
        write_text(SURVEYS, new_surveys)
        write_text(YEAR_TEMPLATE, new_template)

        py_compile.compile(str(SURVEYS), doraise=True)
        Environment().parse(read_text(YEAR_TEMPLATE))

        normalization = normalize_existing_records()

        after = db_state()
        if after["integrity"].lower() != "ok":
            raise RuntimeError("integrity_check không đạt sau cài.")
        if after["fk_count"] != 0:
            raise RuntimeError("foreign_key_check có lỗi sau cài.")
        if after["year_records"] != before["year_records"]:
            raise RuntimeError(
                "Số year-record thay đổi ngoài dự kiến."
            )

        for cache in APP.rglob("__pycache__"):
            if cache.is_dir():
                shutil.rmtree(cache, ignore_errors=True)

    except Exception as exc:
        print()
        print("CÓ LỖI - ĐANG KHÔI PHỤC SOURCE + DATABASE...")
        print(type(exc).__name__ + ":", exc)

        restore_file(SURVEYS)
        restore_file(YEAR_TEMPLATE)
        restore_db()

        for cache in APP.rglob("__pycache__"):
            if cache.is_dir():
                shutil.rmtree(cache, ignore_errors=True)

        print("ĐÃ KHÔI PHỤC.")
        return 9

    lines = [
        "=" * 112,
        "BÁO CÁO CÀI BÀI 13B-12 V2.3.1",
        "=" * 112,
        f"Thời gian: {datetime.now():%d/%m/%Y %H:%M:%S}",
        "",
        "NGUYÊN NHÂN ĐÃ SỬA:",
        "- V2.3 chỉ nhận tên lớp dạng 'Lớp 10', 'Lớp 7'.",
        "- Dữ liệu thực tế có thể là '10', '7', '10A1', '7A'...",
        "- Vì vậy lớp hiện tại có nhưng completed_grade_3/5 vẫn để Chưa xác định.",
        "",
        "V2.3.1:",
        "- Nhận dạng: Lớp 10 / Khối 10 / 10 / 10A1 / 10 A1.",
        "- Không nhầm '5 tuổi' Mầm non thành lớp 5.",
        "- Đang học lớp N -> nếu trống, lớp cao nhất hoàn thành = N-1.",
        "- Lớp 10 -> hoàn thành lớp 9 -> lớp 3 Có -> lớp 5 Có.",
        "- Giữ nguyên: >=15 tuổi vẫn thuộc phạm vi điều tra XMC.",
        "- Thuộc phạm vi XMC không đồng nghĩa mù chữ.",
        "",
        "CHUẨN HÓA DỮ LIỆU HIỆN CÓ:",
        repr(normalization),
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
    print("=" * 112)
    print("CÀI ĐẶT THÀNH CÔNG BÀI 13B-12 V2.3.1")
    print("=" * 112)
    print("Chuẩn hóa:", normalization)
    print("Báo cáo:", REPORT)
    print("Backup:", BACKUP)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
