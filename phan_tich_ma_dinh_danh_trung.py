from __future__ import annotations

import csv
import sys
import unicodedata
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parent
EXPORT_ROOT = PROJECT_DIR / "exports"
REPORT_PREFIX = "kiem_tra_giao_vien_"
SOURCE_NAME = "03_ma_dinh_danh_bi_trung.csv"


def configure_console() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().split())


def comparison_key(value: Any) -> str:
    text = clean_text(value).replace("Đ", "D").replace("đ", "d")
    text = unicodedata.normalize("NFD", text)
    text = "".join(
        character
        for character in text
        if unicodedata.category(character) != "Mn"
    )
    return " ".join(text.lower().split())


def unique_join(rows: list[dict[str, str]], field: str) -> str:
    values: list[str] = []
    seen: set[str] = set()
    for row in rows:
        value = clean_text(row.get(field, ""))
        key = comparison_key(value)
        if value and key not in seen:
            seen.add(key)
            values.append(value)
    return " | ".join(values)


def find_latest_report_dir() -> Path:
    if not EXPORT_ROOT.exists():
        raise FileNotFoundError(f"Không tìm thấy thư mục: {EXPORT_ROOT}")

    candidates = [
        path
        for path in EXPORT_ROOT.iterdir()
        if path.is_dir() and path.name.startswith(REPORT_PREFIX)
    ]
    if not candidates:
        raise FileNotFoundError(
            "Không tìm thấy thư mục báo cáo kiem_tra_giao_vien_* trong exports."
        )

    return max(candidates, key=lambda path: path.stat().st_mtime)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return [dict(row) for row in csv.DictReader(file)]


def write_csv(path: Path, headers: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def classify_group(rows: list[dict[str, str]]) -> tuple[str, str]:
    person_keys = {
        (
            comparison_key(row.get("full_name", "")),
            comparison_key(row.get("date_of_birth", "")),
        )
        for row in rows
    }
    detail_keys = {
        (
            comparison_key(row.get("full_name", "")),
            comparison_key(row.get("date_of_birth", "")),
            comparison_key(row.get("commune_name", "")),
            comparison_key(row.get("school_name", "")),
            comparison_key(row.get("employment_status", "")),
            comparison_key(row.get("job_position", "")),
        )
        for row in rows
    }

    if len(detail_keys) == 1:
        return (
            "TRUNG_BAN_GHI",
            "Các dòng giống nhau về người, đơn vị, trạng thái và vị trí việc làm",
        )
    if len(person_keys) > 1:
        return (
            "XUNG_DOT_NGUOI",
            "Cùng mã định danh nhưng khác họ tên hoặc ngày sinh",
        )
    return (
        "XUNG_DOT_DON_VI",
        "Cùng một người nhưng khác xã, trường, trạng thái hoặc vị trí việc làm",
    )


def main() -> None:
    configure_console()

    print("=" * 78)
    print("BÀI 11B-6A.5 - PHÂN TÍCH MÃ ĐỊNH DANH BỊ TRÙNG")
    print("=" * 78)
    print("Chế độ: chỉ đọc báo cáo, không sửa Excel gốc và không ghi cơ sở dữ liệu.")
    print()

    report_dir = find_latest_report_dir()
    source_path = report_dir / SOURCE_NAME
    if not source_path.exists():
        raise FileNotFoundError(f"Không tìm thấy tệp: {source_path}")

    rows = read_csv(source_path)
    groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        code = clean_text(row.get("staff_code", ""))
        if code:
            groups[code].append(row)

    summary_rows: list[dict[str, Any]] = []
    exact_rows: list[dict[str, Any]] = []
    conflict_rows: list[dict[str, Any]] = []

    counts_by_type: dict[str, int] = defaultdict(int)
    rows_by_type: dict[str, int] = defaultdict(int)

    for staff_code, group_rows in sorted(groups.items()):
        classification, explanation = classify_group(group_rows)
        counts_by_type[classification] += 1
        rows_by_type[classification] += len(group_rows)

        summary = {
            "staff_code": staff_code,
            "so_dong": len(group_rows),
            "phan_loai": classification,
            "giai_thich": explanation,
            "excel_rows": unique_join(group_rows, "excel_row"),
            "full_names": unique_join(group_rows, "full_name"),
            "dates_of_birth": unique_join(group_rows, "date_of_birth"),
            "communes": unique_join(group_rows, "commune_name"),
            "schools": unique_join(group_rows, "school_name"),
            "employment_statuses": unique_join(group_rows, "employment_status"),
            "job_positions": unique_join(group_rows, "job_position"),
        }
        summary_rows.append(summary)

        target = exact_rows if classification == "TRUNG_BAN_GHI" else conflict_rows
        for row in group_rows:
            target.append(
                {
                    **row,
                    "phan_loai": classification,
                    "giai_thich": explanation,
                }
            )

    summary_headers = [
        "staff_code",
        "so_dong",
        "phan_loai",
        "giai_thich",
        "excel_rows",
        "full_names",
        "dates_of_birth",
        "communes",
        "schools",
        "employment_statuses",
        "job_positions",
    ]
    detail_headers = list(rows[0].keys()) if rows else []
    detail_headers += ["phan_loai", "giai_thich"]

    write_csv(
        report_dir / "06_tong_hop_nhom_ma_trung.csv",
        summary_headers,
        summary_rows,
    )
    write_csv(
        report_dir / "07_ma_trung_ban_ghi_giong_nhau.csv",
        detail_headers,
        exact_rows,
    )
    write_csv(
        report_dir / "08_ma_trung_xung_dot.csv",
        detail_headers,
        conflict_rows,
    )

    print(f"Thư mục báo cáo: {report_dir}")
    print(f"Tổng số dòng mã trùng: {len(rows)}")
    print(f"Tổng số mã định danh bị trùng: {len(groups)}")
    print()
    print("PHÂN LOẠI THEO NHÓM MÃ")
    print("-" * 78)
    print(
        "Trùng bản ghi hoàn toàn: "
        f"{counts_by_type['TRUNG_BAN_GHI']} mã / "
        f"{rows_by_type['TRUNG_BAN_GHI']} dòng"
    )
    print(
        "Xung đột người: "
        f"{counts_by_type['XUNG_DOT_NGUOI']} mã / "
        f"{rows_by_type['XUNG_DOT_NGUOI']} dòng"
    )
    print(
        "Xung đột đơn vị hoặc trạng thái: "
        f"{counts_by_type['XUNG_DOT_DON_VI']} mã / "
        f"{rows_by_type['XUNG_DOT_DON_VI']} dòng"
    )
    print()
    print("ĐÃ TẠO CÁC TỆP:")
    print("  06_tong_hop_nhom_ma_trung.csv")
    print("  07_ma_trung_ban_ghi_giong_nhau.csv")
    print("  08_ma_trung_xung_dot.csv")
    print()
    print("HOÀN TẤT: chưa tạo, sửa hoặc xóa bất kỳ tài khoản nào.")


if __name__ == "__main__":
    main()
