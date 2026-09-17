from __future__ import annotations

import csv
import re
import secrets
import sqlite3
import string
import sys
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from app.database import DATABASE_PATH


PROJECT_DIR = Path(__file__).resolve().parent
EXPORT_ROOT = PROJECT_DIR / "exports"
EXPECTED_BASE_SAFE = 12_322
EXPECTED_AUTO_SAFE = 75
EXPECTED_HOLD = 22
EXPECTED_TOTAL_SAFE = 12_397


@dataclass(frozen=True)
class CommuneItem:
    id: int
    code: str
    name: str


@dataclass(frozen=True)
class SchoolItem:
    id: int
    code: str
    name: str
    commune_id: int | None
    commune_name: str


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
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def commune_key(value: Any) -> str:
    key = comparison_key(value)
    for prefix in ("uy ban nhan dan ", "ubnd "):
        if key.startswith(prefix):
            return key[len(prefix):].strip()
    return key


def school_exact_key(value: Any) -> str:
    return comparison_key(value)


def school_loose_key(value: Any) -> str:
    key = comparison_key(value)
    replacements = (
        (r"\btruong mam non\b", " mn "),
        (r"\bco so mam non\b", " cs mn "),
        (r"\btruong tieu hoc\b", " th "),
        (r"\btruong trung hoc co so\b", " thcs "),
        (r"\btruong trung hoc pho thong\b", " thpt "),
    )
    for pattern, replacement in replacements:
        key = re.sub(pattern, replacement, key)
    return " ".join(key.split())


def normalize_staff_code(value: Any) -> str:
    text = clean_text(value).upper()
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    return re.sub(r"\s+", "", text)


def is_active_status(value: Any) -> bool:
    key = comparison_key(value)
    active_terms = (
        "dang lam viec",
        "dang cong tac",
        "cong tac",
        "dang lam",
    )
    return any(term == key or term in key for term in active_terms)


def determine_role(value: Any) -> tuple[str, str] | None:
    key = comparison_key(value)
    if "giao vien" in key:
        return "GIAO_VIEN", "Giáo viên"
    manager_terms = (
        "can bo quan ly",
        "hieu truong",
        "pho hieu truong",
        "giam doc",
        "pho giam doc",
    )
    if any(term in key for term in manager_terms):
        return "TRUONG", "Trường"
    return None


def normalize_username(value: Any) -> str:
    return re.sub(r"[^a-z0-9._-]+", "", clean_text(value).lower())


def proposed_username(role_code: str, staff_code: str) -> str:
    prefix = "gv" if role_code == "GIAO_VIEN" else "cbql"
    return normalize_username(f"{prefix}.{staff_code}")[:100]


def random_password(length: int = 14) -> str:
    alphabet = string.ascii_letters + string.digits
    while True:
        password = "Pc!" + "".join(secrets.choice(alphabet) for _ in range(length - 3))
        if (
            any(c.islower() for c in password)
            and any(c.isupper() for c in password)
            and any(c.isdigit() for c in password)
        ):
            return password


def latest_report_dir() -> Path:
    candidates = [
        path
        for path in EXPORT_ROOT.glob("kiem_tra_giao_vien_*")
        if path.is_dir()
    ]
    if not candidates:
        raise FileNotFoundError(
            f"Không tìm thấy thư mục báo cáo trong {EXPORT_ROOT}."
        )
    return max(candidates, key=lambda path: path.stat().st_mtime)


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"Không tìm thấy tệp bắt buộc: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def first_value(row: dict[str, Any], names: Iterable[str]) -> str:
    normalized = {comparison_key(key): value for key, value in row.items()}
    for name in names:
        value = normalized.get(comparison_key(name))
        if clean_text(value):
            return clean_text(value)
    return ""


def load_database_catalogs() -> tuple[
    list[CommuneItem],
    list[SchoolItem],
    dict[str, int],
    set[str],
]:
    connection = sqlite3.connect(str(DATABASE_PATH))
    connection.row_factory = sqlite3.Row

    communes = [
        CommuneItem(
            id=int(row["id"]),
            code=clean_text(row["code"]),
            name=clean_text(row["name"]),
        )
        for row in connection.execute(
            "SELECT id, code, name FROM communes ORDER BY name"
        )
    ]

    school_columns = {
        row[1]
        for row in connection.execute("PRAGMA table_info(schools)")
    }
    school_code_sql = "s.code" if "code" in school_columns else "''"
    schools = [
        SchoolItem(
            id=int(row["id"]),
            code=clean_text(row["code"]),
            name=clean_text(row["name"]),
            commune_id=(
                int(row["commune_id"])
                if row["commune_id"] is not None
                else None
            ),
            commune_name=clean_text(row["commune_name"]),
        )
        for row in connection.execute(
            f"""
            SELECT
                s.id,
                {school_code_sql} AS code,
                s.name,
                s.commune_id,
                c.name AS commune_name
            FROM schools AS s
            LEFT JOIN communes AS c ON c.id = s.commune_id
            ORDER BY s.name
            """
        )
    ]

    role_ids = {
        clean_text(row["code"]).upper(): int(row["id"])
        for row in connection.execute("SELECT id, code FROM roles")
    }
    existing_usernames = {
        normalize_username(row["username"])
        for row in connection.execute("SELECT username FROM users")
        if clean_text(row["username"])
    }

    connection.close()
    return communes, schools, role_ids, existing_usernames


def build_indexes(
    communes: Iterable[CommuneItem],
    schools: Iterable[SchoolItem],
) -> tuple[
    dict[str, list[CommuneItem]],
    dict[tuple[int, str], list[SchoolItem]],
    dict[tuple[int, str], list[SchoolItem]],
    dict[str, list[SchoolItem]],
    dict[str, list[SchoolItem]],
]:
    commune_index: dict[str, list[CommuneItem]] = defaultdict(list)
    exact_by_commune: dict[tuple[int, str], list[SchoolItem]] = defaultdict(list)
    loose_by_commune: dict[tuple[int, str], list[SchoolItem]] = defaultdict(list)
    exact_global: dict[str, list[SchoolItem]] = defaultdict(list)
    loose_global: dict[str, list[SchoolItem]] = defaultdict(list)

    for commune in communes:
        commune_index[commune_key(commune.name)].append(commune)

    for school in schools:
        exact = school_exact_key(school.name)
        loose = school_loose_key(school.name)
        exact_global[exact].append(school)
        loose_global[loose].append(school)
        if school.commune_id is not None:
            exact_by_commune[(school.commune_id, exact)].append(school)
            loose_by_commune[(school.commune_id, loose)].append(school)

    return (
        commune_index,
        exact_by_commune,
        loose_by_commune,
        exact_global,
        loose_global,
    )


def resolve_commune_school(
    commune_name: str,
    school_name: str,
    communes: list[CommuneItem],
    indexes: tuple[
        dict[str, list[CommuneItem]],
        dict[tuple[int, str], list[SchoolItem]],
        dict[tuple[int, str], list[SchoolItem]],
        dict[str, list[SchoolItem]],
        dict[str, list[SchoolItem]],
    ],
) -> tuple[CommuneItem | None, SchoolItem | None, list[str]]:
    (
        commune_index,
        exact_by_commune,
        loose_by_commune,
        exact_global,
        loose_global,
    ) = indexes

    errors: list[str] = []
    commune: CommuneItem | None = None
    school: SchoolItem | None = None

    if commune_name:
        matches = commune_index.get(commune_key(commune_name), [])
        if len(matches) == 1:
            commune = matches[0]
        elif len(matches) == 0:
            errors.append("Không tìm thấy xã/phường trong cơ sở dữ liệu")
        else:
            errors.append("Tên xã/phường khớp nhiều danh mục")

    exact = school_exact_key(school_name)
    loose = school_loose_key(school_name)
    school_candidates: list[SchoolItem] = []

    if commune is not None:
        school_candidates = exact_by_commune.get((commune.id, exact), [])
        if not school_candidates:
            school_candidates = loose_by_commune.get((commune.id, loose), [])
    else:
        # Trường trực thuộc Sở: ưu tiên khớp tên chính xác và commune_id trống.
        direct_exact = [
            item for item in exact_global.get(exact, [])
            if item.commune_id is None
        ]
        if len(direct_exact) == 1:
            school_candidates = direct_exact
        elif not direct_exact:
            global_exact = exact_global.get(exact, [])
            if len(global_exact) == 1:
                school_candidates = global_exact
            else:
                direct_loose = [
                    item for item in loose_global.get(loose, [])
                    if item.commune_id is None
                ]
                if len(direct_loose) == 1:
                    school_candidates = direct_loose

    if len(school_candidates) == 1:
        school = school_candidates[0]
        if commune is None and school.commune_id is not None:
            commune = next(
                (item for item in communes if item.id == school.commune_id),
                None,
            )
    elif len(school_candidates) == 0:
        errors.append("Không tìm thấy trường tương ứng với xã/phường")
    else:
        errors.append("Tên trường khớp nhiều danh mục")

    if school is not None and school.commune_id != (commune.id if commune else None):
        if not (school.commune_id is None and commune is None):
            errors.append("Trường không thuộc xã/phường đã xác định")

    return commune, school, errors


def choose_auto_safe_rows(
    safe_codes: set[str],
    detail_rows: list[dict[str, str]],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in detail_rows:
        code = normalize_staff_code(
            first_value(row, ("staff_code", "Mã định danh Bộ GD&ĐT"))
        )
        if code in safe_codes:
            grouped[code].append(row)

    selected: list[dict[str, str]] = []
    errors: list[dict[str, str]] = []

    for code in sorted(safe_codes):
        candidates = []
        for row in grouped.get(code, []):
            status = first_value(row, ("employment_status", "Trạng thái"))
            position = first_value(row, ("job_position", "Vị trí việc làm"))
            if is_active_status(status) and determine_role(position) is not None:
                candidates.append(row)

        if not candidates:
            errors.append({
                "staff_code": code,
                "reason": "Không tìm thấy dòng đang làm việc thuộc phạm vi nhập",
            })
            continue

        signatures = {
            (
                comparison_key(first_value(row, ("full_name", "Họ tên"))),
                comparison_key(first_value(row, ("date_of_birth", "Ngày sinh"))),
                commune_key(first_value(row, ("commune_name", "UBND Xã"))),
                school_exact_key(first_value(row, ("school_name", "Tên trường"))),
                comparison_key(first_value(row, ("job_position", "Vị trí việc làm"))),
            )
            for row in candidates
        }
        if len(signatures) > 1:
            errors.append({
                "staff_code": code,
                "reason": "Các dòng đang làm việc không giống nhau; không thể tự chọn",
            })
            continue

        candidates.sort(
            key=lambda row: int(
                re.sub(
                    r"\D",
                    "",
                    first_value(row, ("excel_row", "Dòng Excel")),
                ) or "999999999"
            )
        )
        selected.append(candidates[0])

    return selected, errors


def write_csv(path: Path, headers: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    configure_console()

    print("=" * 78)
    print("BÀI 11B-6A.8 - LẬP KẾ HOẠCH NHẬP TÀI KHOẢN AN TOÀN")
    print("=" * 78)
    print("Chế độ: CHỈ LẬP KẾ HOẠCH, CHƯA GHI VÀO BẢNG users.")
    print()

    report_dir = latest_report_dir()
    print(f"Thư mục báo cáo: {report_dir}")

    base_rows = read_csv(report_dir / "01_du_kien_tao_tai_khoan.csv")
    auto_summary = read_csv(report_dir / "10_ma_co_the_xu_ly_tu_dong.csv")
    hold_summary = read_csv(report_dir / "11_ma_bat_buoc_kiem_tra.csv")
    detail_rows = read_csv(report_dir / "12_chi_tiet_day_du_ma_trung.csv")

    auto_codes = {
        normalize_staff_code(first_value(row, ("staff_code", "Mã định danh Bộ GD&ĐT")))
        for row in auto_summary
        if normalize_staff_code(first_value(row, ("staff_code", "Mã định danh Bộ GD&ĐT")))
    }
    hold_codes = {
        normalize_staff_code(first_value(row, ("staff_code", "Mã định danh Bộ GD&ĐT")))
        for row in hold_summary
        if normalize_staff_code(first_value(row, ("staff_code", "Mã định danh Bộ GD&ĐT")))
    }

    auto_rows, auto_errors = choose_auto_safe_rows(auto_codes, detail_rows)

    communes, schools, role_ids, existing_usernames = load_database_catalogs()
    indexes = build_indexes(communes, schools)

    errors: list[dict[str, Any]] = list(auto_errors)
    plans: list[dict[str, Any]] = []
    seen_codes: set[str] = set()
    seen_usernames: set[str] = set(existing_usernames)

    def add_plan(source_row: dict[str, Any], source_group: str) -> None:
        staff_code = normalize_staff_code(
            first_value(source_row, ("staff_code", "Mã định danh Bộ GD&ĐT"))
        )
        full_name = first_value(source_row, ("full_name", "Họ tên", "Họ và tên"))
        commune_name = first_value(source_row, ("commune_name", "UBND Xã", "Xã/phường"))
        school_name = first_value(source_row, ("school_name", "Tên trường", "Trường"))
        job_position = first_value(source_row, ("job_position", "Vị trí việc làm"))
        date_of_birth = first_value(source_row, ("date_of_birth", "Ngày sinh"))

        row_errors: list[str] = []
        if not staff_code:
            row_errors.append("Thiếu mã định danh")
        if staff_code in hold_codes:
            row_errors.append("Mã thuộc danh sách 22 trường hợp giữ lại")
        if staff_code in seen_codes:
            row_errors.append("Mã định danh bị lặp trong kế hoạch")
        if not full_name:
            row_errors.append("Thiếu họ tên")

        role = determine_role(job_position)
        if role is None:
            role_code = ""
            role_name = ""
            row_errors.append("Không xác định được vai trò")
        else:
            role_code, role_name = role

        role_id = role_ids.get(role_code)
        if role_code and role_id is None:
            row_errors.append(f"Không tìm thấy vai trò {role_code} trong bảng roles")

        commune, school, resolve_errors = resolve_commune_school(
            commune_name,
            school_name,
            communes,
            indexes,
        )
        row_errors.extend(resolve_errors)

        username = normalize_username(
            first_value(source_row, ("username_proposed", "username"))
        )
        if not username and role_code and staff_code:
            username = proposed_username(role_code, staff_code)
        if not username:
            row_errors.append("Không tạo được tên đăng nhập")
        elif username in seen_usernames:
            row_errors.append("Tên đăng nhập đã tồn tại hoặc bị lặp")

        if row_errors:
            errors.append({
                "source_group": source_group,
                "staff_code": staff_code,
                "full_name": full_name,
                "commune_name": commune_name,
                "school_name": school_name,
                "job_position": job_position,
                "reason": "; ".join(dict.fromkeys(row_errors)),
            })
            return

        plans.append({
            "stt": len(plans) + 1,
            "username": username,
            "initial_password": random_password(),
            "full_name": full_name,
            "staff_code": staff_code,
            "date_of_birth": date_of_birth,
            "role_id": role_id,
            "role_code": role_code,
            "role_name": role_name,
            "commune_id": commune.id if commune else "",
            "commune_code": commune.code if commune else "",
            "commune_name": commune.name if commune else "",
            "school_id": school.id if school else "",
            "school_code": school.code if school else "",
            "school_name": school.name if school else "",
            "is_active": 1,
            "source_group": source_group,
            "source_excel_row": first_value(source_row, ("excel_row", "Dòng Excel")),
        })
        seen_codes.add(staff_code)
        seen_usernames.add(username)

    for row in base_rows:
        add_plan(row, "01_DU_KIEN_HOP_LE")

    for row in auto_rows:
        add_plan(row, "10_MA_TRUNG_XU_LY_TU_DONG")

    plan_path = report_dir / "14_ke_hoach_nhap_tai_khoan_an_toan.csv"
    error_path = report_dir / "15_loi_ke_hoach_nhap_tai_khoan.csv"
    hold_path = report_dir / "16_danh_sach_22_ma_giu_lai.csv"

    plan_headers = [
        "stt",
        "username",
        "initial_password",
        "full_name",
        "staff_code",
        "date_of_birth",
        "role_id",
        "role_code",
        "role_name",
        "commune_id",
        "commune_code",
        "commune_name",
        "school_id",
        "school_code",
        "school_name",
        "is_active",
        "source_group",
        "source_excel_row",
    ]
    error_headers = [
        "source_group",
        "staff_code",
        "full_name",
        "commune_name",
        "school_name",
        "job_position",
        "reason",
    ]

    write_csv(plan_path, plan_headers, plans)
    write_csv(error_path, error_headers, errors)
    write_csv(
        hold_path,
        list(hold_summary[0].keys()) if hold_summary else ["staff_code"],
        hold_summary,
    )

    base_plan_count = sum(
        1 for row in plans if row["source_group"] == "01_DU_KIEN_HOP_LE"
    )
    auto_plan_count = sum(
        1 for row in plans if row["source_group"] == "10_MA_TRUNG_XU_LY_TU_DONG"
    )

    print()
    print("KẾT QUẢ LẬP KẾ HOẠCH")
    print("-" * 78)
    print(f"Dòng hợp lệ ban đầu trong báo cáo: {len(base_rows)}")
    print(f"Mã trùng có thể xử lý tự động: {len(auto_codes)}")
    print(f"Mã giữ lại, chưa nhập: {len(hold_codes)}")
    print(f"Tài khoản từ nhóm hợp lệ: {base_plan_count}")
    print(f"Tài khoản từ nhóm xử lý tự động: {auto_plan_count}")
    print(f"TỔNG TÀI KHOẢN TRONG KẾ HOẠCH: {len(plans)}")
    print(f"Lỗi còn lại trong kế hoạch: {len(errors)}")
    print()

    expected_ok = (
        len(base_rows) == EXPECTED_BASE_SAFE
        and len(auto_codes) == EXPECTED_AUTO_SAFE
        and len(hold_codes) == EXPECTED_HOLD
        and len(plans) == EXPECTED_TOTAL_SAFE
        and len(errors) == 0
    )

    if expected_ok:
        print("TRẠNG THÁI: ĐỦ ĐIỀU KIỆN CHUYỂN SANG BƯỚC NHẬP.")
    else:
        print("TRẠNG THÁI: CHƯA ĐƯỢC NHẬP - SỐ LIỆU KHÔNG KHỚP DỰ KIẾN.")
        print("Hãy kiểm tra tệp 15_loi_ke_hoach_nhap_tai_khoan.csv.")

    print()
    print("ĐÃ TẠO CÁC TỆP:")
    print(f"  {plan_path.name}")
    print(f"  {error_path.name}")
    print(f"  {hold_path.name}")
    print()
    print("LƯU Ý BẢO MẬT:")
    print("Tệp 14 có mật khẩu khởi tạo riêng cho từng tài khoản.")
    print("Không gửi công khai và không đưa tệp này lên Internet.")
    print()
    print("HOÀN TẤT: chưa có tài khoản nào được ghi vào bảng users.")


if __name__ == "__main__":
    main()
