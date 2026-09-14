from __future__ import annotations

import ast
import os
import re
import sqlite3
import traceback
from datetime import datetime
from pathlib import Path

PROJECT = Path(os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")).resolve()
APP = PROJECT / "app"
EXPORTS = PROJECT / "exports"
DB = PROJECT / "data" / "phocap.db"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
REPORT = EXPORTS / f"khao_sat_bai_13b_11_13_3_0_{STAMP}.txt"

TEXT_EXT = {".py", ".html", ".htm", ".js"}

PHRASES = [
    "chưa đủ 8 chỉ báo",
    "đủ 8 chỉ báo",
    "Chỉ báo:",
    "0/8",
    "criteria_answered",
    "criteria_total",
    "current_year_answered",
    "current_year_total",
    "completed_preschool_5",
    "attends_required_days",
    "attends_regularly",
    "prepared_vietnamese",
    "weight_monitored",
    "underweight",
    "height_monitored",
    "stunted",
    "Các chỉ báo mầm non",
    "Các chỉ báo Tiểu học",
    "Các chỉ báo THCS",
    "Theo dõi trẻ khuyết tật",
    "Không thể hoàn thành phiếu",
    "Chưa nhập đủ chỉ báo",
    "nhap-nhanh",
    "cap-nhat",
]

TARGET_FILES = [
    APP / "templates" / "surveys" / "year_records.html",
    APP / "templates" / "surveys" / "quick_entry.html",
    APP / "templates" / "surveys" / "form_edit.html",
    APP / "routers" / "surveys.py",
]


def add(out: list[str], text: str = "") -> None:
    out.append(text)


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")


def section(out: list[str], title: str) -> None:
    add(out)
    add(out, "=" * 118)
    add(out, title)
    add(out, "=" * 118)


def context(lines: list[str], line_no: int, before: int = 12, after: int = 22) -> list[str]:
    start = max(1, line_no - before)
    end = min(len(lines), line_no + after)
    result = []
    for n in range(start, end + 1):
        prefix = ">" if n == line_no else " "
        result.append(f"{prefix} {n:5}: {lines[n-1]}")
    return result


def scan_exact_files(out: list[str]) -> None:
    section(out, "1. CÁC TỆP MỤC TIÊU")

    for path in TARGET_FILES:
        rel = path.relative_to(PROJECT)
        add(out, f"[{rel}]")

        if not path.exists():
            add(out, "  - Không tồn tại.")
            continue

        text = read_text(path)
        lines = text.splitlines()
        add(out, f"  - Số dòng: {len(lines)}")

        markers = [
            "BAI_13B_11_13_2_4_STRICT_UI_START",
            "BAI_13B_11_13_2_3_EXCLUSIVE_LEVEL_START",
            "BAI_13B_11_13_2_LEVEL_UI_START",
            "BAI_13B_11_13_2_XMC_UI_START",
        ]

        for marker in markers:
            add(
                out,
                f"  - {marker}: {'CÓ' if marker in text else 'KHÔNG'}",
            )


def scan_phrases(out: list[str]) -> None:
    section(out, "2. TÌM LOGIC 8 CHỈ BÁO / HOÀN THÀNH PHIẾU / NHẬP NHANH")

    files = [
        p
        for p in APP.rglob("*")
        if p.is_file()
        and p.suffix.lower() in TEXT_EXT
        and "__pycache__" not in p.parts
    ]

    hit_count = 0

    for path in files:
        text = read_text(path)
        lines = text.splitlines()
        lower_lines = [line.lower() for line in lines]

        matching_lines: list[int] = []

        for idx, lower in enumerate(lower_lines, start=1):
            if any(phrase.lower() in lower for phrase in PHRASES):
                matching_lines.append(idx)

        if not matching_lines:
            continue

        # Chỉ in các tệp thật sự liên quan đến survey/household.
        rel = str(path.relative_to(PROJECT)).lower()
        if not any(
            token in rel
            for token in (
                "survey",
                "household",
                "quick",
                "year_record",
                "people",
            )
        ):
            continue

        hit_count += 1
        add(out)
        add(out, f"[FILE] {path.relative_to(PROJECT)}")
        add(out, f"  Tổng dòng khớp: {len(matching_lines)}")

        # Gom các dòng gần nhau để tránh in trùng context.
        selected = []
        last = -999
        for line_no in matching_lines:
            if line_no - last >= 18:
                selected.append(line_no)
                last = line_no
            if len(selected) >= 18:
                break

        for line_no in selected:
            add(out)
            add(out, f"--- Context quanh dòng {line_no} ---")
            add(out, "\n".join(context(lines, line_no)))

    if hit_count == 0:
        add(out, "Không tìm thấy tệp liên quan.")


def inspect_year_template_structure(out: list[str]) -> None:
    path = APP / "templates" / "surveys" / "year_records.html"
    section(out, "3. CẤU TRÚC year_records.html HIỆN TẠI")

    if not path.exists():
        add(out, "Không tìm thấy year_records.html.")
        return

    text = read_text(path)
    lines = text.splitlines()

    targets = [
        "Các chỉ báo mầm non",
        "BAI_13B_11_13_2_LEVEL_UI_START",
        "b131132_primary_indicators",
        "b131132_thcs_indicators",
        "Theo dõi trẻ khuyết tật",
        'id="disability_status"',
        "BAI_13B_11_13_2_4_STRICT_UI_START",
    ]

    for target in targets:
        indexes = [
            idx
            for idx, line in enumerate(lines, start=1)
            if target.lower() in line.lower()
        ]

        add(out)
        add(out, f"[{target}] -> {indexes}")

        for line_no in indexes[:3]:
            add(out, "\n".join(context(lines, line_no, 8, 16)))


def inspect_python_functions(out: list[str]) -> None:
    section(out, "4. HÀM PYTHON CÓ KHẢ NĂNG TÍNH CHỈ BÁO / CHẶN HOÀN THÀNH")

    for path in (APP / "routers").rglob("*.py"):
        if "__pycache__" in path.parts:
            continue

        text = read_text(path)

        if not any(
            phrase.lower() in text.lower()
            for phrase in (
                "criteria_answered",
                "criteria_total",
                "chỉ báo",
                "chi_bao",
                "completed_preschool_5",
            )
        ):
            continue

        try:
            tree = ast.parse(text)
        except Exception:
            continue

        lines = text.splitlines()

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue

            segment = ast.get_source_segment(text, node) or ""
            lowered = segment.lower()

            score = 0
            for token in (
                "criteria_answered",
                "criteria_total",
                "completed_preschool_5",
                "attends_required_days",
                "stunted",
                "hoàn thành phiếu",
                "chưa đủ",
                "nhap-nhanh",
            ):
                if token.lower() in lowered:
                    score += 1

            if score < 2:
                continue

            add(out)
            add(
                out,
                f"[FUNCTION] {path.relative_to(PROJECT)}::{node.name} "
                f"(dòng {node.lineno}-{node.end_lineno}, score={score})",
            )

            start = max(1, node.lineno)
            end = min(len(lines), node.end_lineno or node.lineno, start + 180)

            for n in range(start, end + 1):
                add(out, f"{n:5}: {lines[n-1]}")


def inspect_db(out: list[str]) -> None:
    section(out, "5. DATABASE - CHỈ ĐỌC")

    if not DB.exists():
        add(out, f"Không tìm thấy DB: {DB}")
        return

    uri = f"file:{DB.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)

    try:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        fk = len(conn.execute("PRAGMA foreign_key_check").fetchall())
        add(out, f"integrity_check = {integrity}")
        add(out, f"foreign_key_check = {fk} lỗi")

        cols = conn.execute(
            "PRAGMA table_info(survey_person_year_records)"
        ).fetchall()

        add(out, "survey_person_year_records columns:")
        for row in cols:
            add(out, f" - {row[1]} ({row[2]})")
    finally:
        conn.close()


def main() -> int:
    out: list[str] = []

    add(out, "=" * 118)
    add(out, "BÀI 13B-11.13.3.0 - KHẢO SÁT LOGIC CHỈ BÁO THEO CẤP VÀ ĐIỀU KIỆN HOÀN THÀNH PHIẾU")
    add(out, "=" * 118)
    add(out)
    add(out, "CHẾ ĐỘ: CHỈ ĐỌC")
    add(out, " - Không sửa source.")
    add(out, " - Không sửa database.")
    add(out, " - Mục tiêu: tìm đúng chỗ đang cố định 8 chỉ báo Mầm non cho mọi đối tượng.")

    try:
        scan_exact_files(out)
        scan_phrases(out)
        inspect_year_template_structure(out)
        inspect_python_functions(out)
        inspect_db(out)

        EXPORTS.mkdir(parents=True, exist_ok=True)
        REPORT.write_text("\n".join(out), encoding="utf-8")

        print("\n".join(out[:70]))
        print()
        if len(out) > 70:
            print("... báo cáo đầy đủ đã ghi ra file ...")
        print()
        print("=" * 118)
        print("KHẢO SÁT BÀI 13B-11.13.3.0 HOÀN THÀNH")
        print("=" * 118)
        print("Không có source/database nào bị thay đổi.")
        print("Báo cáo:")
        print(REPORT)
        return 0

    except Exception:
        traceback.print_exc()
        try:
            EXPORTS.mkdir(parents=True, exist_ok=True)
            out.append("")
            out.append("KHẢO SÁT DỪNG DO LỖI.")
            out.append(traceback.format_exc())
            REPORT.write_text("\n".join(out), encoding="utf-8")
            print("Báo cáo lỗi:")
            print(REPORT)
        except Exception:
            pass

        print("Source/database không bị thay đổi.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
