from __future__ import annotations

import csv
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parent
EXPORT_ROOT = PROJECT_DIR / "exports"
REPORT_PREFIX = "kiem_tra_giao_vien_"
DUPLICATE_SOURCE = "03_ma_dinh_danh_bi_trung.csv"
IGNORED_SOURCE = "04_dong_khong_nhap.csv"


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


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return [dict(row) for row in csv.DictReader(file)]


def write_csv(
    path: Path,
    headers: list[str],
    rows: list[dict[str, Any]],
) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=headers,
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)


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


def person_key(row: dict[str, str]) -> tuple[str, str]:
    return (
        comparison_key(row.get("full_name", "")),
        comparison_key(row.get("date_of_birth", "")),
    )


def detail_key(row: dict[str, str]) -> tuple[str, ...]:
    return (
        comparison_key(row.get("full_name", "")),
        comparison_key(row.get("date_of_birth", "")),
        comparison_key(row.get("commune_name", "")),
        comparison_key(row.get("school_name", "")),
        comparison_key(row.get("employment_status", "")),
        comparison_key(row.get("job_position", "")),
    )


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


def classify_group(
    eligible_rows: list[dict[str, str]],
    ignored_rows: list[dict[str, str]],
) -> tuple[str, str, str]:
    all_rows = eligible_rows + ignored_rows
    identities = {person_key(row) for row in all_rows}
    eligible_details = {detail_key(row) for row in eligible_rows}

    if len(identities) > 1:
        return (
            "XUNG_DOT_NGUOI",
            "BẮT BUỘC KIỂM TRA",
            "Cùng mã định danh nhưng khác họ tên hoặc ngày sinh.",
        )

    if len(eligible_rows) >= 2:
        if len(eligible_details) == 1:
            return (
                "TRUNG_DONG_DU_DIEU_KIEN",
                "GIỮ 1 DÒNG",
                "Có nhiều dòng đủ điều kiện giống nhau; chỉ được tạo một tài khoản.",
            )
        return (
            "XUNG_DOT_DON_VI_DU_DIEU_KIEN",
            "BẮT BUỘC KIỂM TRA",
            "Cùng người nhưng có nhiều dòng đủ điều kiện khác đơn vị, trạng thái hoặc vị trí.",
        )

    if len(eligible_rows) == 1 and ignored_rows:
        ignored_reasons = [comparison_key(row.get("reason", "")) for row in ignored_rows]
        only_old_status = all(
            "khong o trang thai dang lam viec" in reason
            for reason in ignored_reasons
        )
        if only_old_status:
            return (
                "CO_THE_DUNG_BAN_GHI_DANG_LAM_VIEC",
                "CÓ THỂ DÙNG DÒNG ĐỦ ĐIỀU KIỆN",
                "Chỉ có một dòng đang làm việc; các dòng còn lại không còn ở trạng thái đang làm việc.",
            )
        return (
            "CAN_XAC_MINH_VI_TRI_HOAC_PHAM_VI",
            "CẦN KIỂM TRA",
            "Chỉ có một dòng đủ điều kiện nhưng còn dòng cùng người bị loại do vị trí hoặc phạm vi nhập.",
        )

    return (
        "KHONG_DU_THONG_TIN_PHAN_LOAI",
        "CẦN KIỂM TRA",
        "Không đủ dữ liệu đối chiếu để tự quyết định.",
    )


def main() -> None:
    configure_console()

    print("=" * 78)
    print("BÀI 11B-6A.6 - PHÂN TÍCH ĐẦY ĐỦ MÃ ĐỊNH DANH BỊ TRÙNG")
    print("=" * 78)
    print("Chế độ: chỉ đọc báo cáo, không sửa Excel và không ghi cơ sở dữ liệu.")
    print()

    report_dir = find_latest_report_dir()
    duplicate_path = report_dir / DUPLICATE_SOURCE
    ignored_path = report_dir / IGNORED_SOURCE

    if not duplicate_path.exists():
        raise FileNotFoundError(f"Không tìm thấy tệp: {duplicate_path}")
    if not ignored_path.exists():
        raise FileNotFoundError(f"Không tìm thấy tệp: {ignored_path}")

    eligible_duplicate_rows = read_csv(duplicate_path)
    ignored_all_rows = read_csv(ignored_path)

    duplicated_codes = {
        clean_text(row.get("staff_code", ""))
        for row in eligible_duplicate_rows
        if clean_text(row.get("staff_code", ""))
    }

    eligible_by_code: dict[str, list[dict[str, str]]] = defaultdict(list)
    ignored_by_code: dict[str, list[dict[str, str]]] = defaultdict(list)

    for row in eligible_duplicate_rows:
        code = clean_text(row.get("staff_code", ""))
        if code:
            eligible_by_code[code].append(row)

    for row in ignored_all_rows:
        code = clean_text(row.get("staff_code", ""))
        if code in duplicated_codes:
            ignored_by_code[code].append(row)

    summary_rows: list[dict[str, Any]] = []
    detail_rows: list[dict[str, Any]] = []
    usable_rows: list[dict[str, Any]] = []
    review_rows: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()

    for code in sorted(duplicated_codes):
        eligible_rows = eligible_by_code.get(code, [])
        ignored_rows = ignored_by_code.get(code, [])
        classification, recommendation, explanation = classify_group(
            eligible_rows,
            ignored_rows,
        )
        counts[classification] += 1
        all_rows = eligible_rows + ignored_rows

        summary = {
            "staff_code": code,
            "phan_loai": classification,
            "khuyen_nghi": recommendation,
            "giai_thich": explanation,
            "so_dong_du_dieu_kien": len(eligible_rows),
            "so_dong_khong_nhap": len(ignored_rows),
            "tong_so_dong_doi_chieu": len(all_rows),
            "excel_rows": unique_join(all_rows, "excel_row"),
            "full_names": unique_join(all_rows, "full_name"),
            "dates_of_birth": unique_join(all_rows, "date_of_birth"),
            "communes": unique_join(all_rows, "commune_name"),
            "schools": unique_join(all_rows, "school_name"),
            "employment_statuses": unique_join(all_rows, "employment_status"),
            "job_positions": unique_join(all_rows, "job_position"),
            "ignored_reasons": unique_join(ignored_rows, "reason"),
        }
        summary_rows.append(summary)

        safe_classes = {
            "TRUNG_DONG_DU_DIEU_KIEN",
            "CO_THE_DUNG_BAN_GHI_DANG_LAM_VIEC",
        }
        if classification in safe_classes:
            usable_rows.append(summary)
        else:
            review_rows.append(summary)

        for source_name, source_rows in (
            ("DU_DIEU_KIEN_NEU_KHONG_TRUNG_MA", eligible_rows),
            ("DONG_KHONG_NHAP", ignored_rows),
        ):
            for row in source_rows:
                detail_rows.append(
                    {
                        **row,
                        "nguon_doi_chieu": source_name,
                        "phan_loai_nhom": classification,
                        "khuyen_nghi": recommendation,
                        "giai_thich_nhom": explanation,
                    }
                )

    summary_headers = [
        "staff_code",
        "phan_loai",
        "khuyen_nghi",
        "giai_thich",
        "so_dong_du_dieu_kien",
        "so_dong_khong_nhap",
        "tong_so_dong_doi_chieu",
        "excel_rows",
        "full_names",
        "dates_of_birth",
        "communes",
        "schools",
        "employment_statuses",
        "job_positions",
        "ignored_reasons",
    ]

    detail_headers: list[str] = []
    for row in detail_rows:
        for key in row:
            if key not in detail_headers:
                detail_headers.append(key)

    write_csv(
        report_dir / "09_tong_hop_ma_trung_day_du.csv",
        summary_headers,
        summary_rows,
    )
    write_csv(
        report_dir / "10_ma_co_the_xu_ly_tu_dong.csv",
        summary_headers,
        usable_rows,
    )
    write_csv(
        report_dir / "11_ma_bat_buoc_kiem_tra.csv",
        summary_headers,
        review_rows,
    )
    write_csv(
        report_dir / "12_chi_tiet_day_du_ma_trung.csv",
        detail_headers,
        detail_rows,
    )

    print(f"Thư mục báo cáo: {report_dir}")
    print(f"Số mã được phân tích: {len(duplicated_codes)}")
    print()
    print("PHÂN LOẠI ĐẦY ĐỦ")
    print("-" * 78)
    labels = [
        ("CO_THE_DUNG_BAN_GHI_DANG_LAM_VIEC", "Có thể dùng bản ghi đang làm việc"),
        ("TRUNG_DONG_DU_DIEU_KIEN", "Trùng dòng đủ điều kiện - giữ một dòng"),
        ("CAN_XAC_MINH_VI_TRI_HOAC_PHAM_VI", "Cần xác minh vị trí hoặc phạm vi"),
        ("XUNG_DOT_DON_VI_DU_DIEU_KIEN", "Xung đột đơn vị giữa các dòng đủ điều kiện"),
        ("XUNG_DOT_NGUOI", "Xung đột người"),
        ("KHONG_DU_THONG_TIN_PHAN_LOAI", "Không đủ thông tin phân loại"),
    ]
    for key, label in labels:
        print(f"{label}: {counts[key]} mã")

    print()
    print(f"Có thể xử lý tự động: {len(usable_rows)} mã")
    print(f"Bắt buộc kiểm tra: {len(review_rows)} mã")
    print()
    print("ĐÃ TẠO CÁC TỆP:")
    print("  09_tong_hop_ma_trung_day_du.csv")
    print("  10_ma_co_the_xu_ly_tu_dong.csv")
    print("  11_ma_bat_buoc_kiem_tra.csv")
    print("  12_chi_tiet_day_du_ma_trung.csv")
    print()
    print("HOÀN TẤT: chưa tạo, sửa hoặc xóa bất kỳ tài khoản nào.")


if __name__ == "__main__":
    main()
