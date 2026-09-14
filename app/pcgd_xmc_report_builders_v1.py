from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from io import BytesIO
from pathlib import Path
import json
import re
import unicodedata
from typing import Any

from fastapi.responses import StreamingResponse
from openpyxl import load_workbook
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Classroom, Commune, School, SchoolYear
from app.staff_models import StaffMember, StaffYearRecord
from app.report_input_models import SchoolNetworkYearData, SchoolStructuredReportInput
from app.structured_report_catalog import STRUCTURED_FORM_BY_CODE, flatten_fields
from app.permissions import (
    COMMUNE_ROLE_CODE,
    SCHOOL_ROLE_CODE,
    TEACHER_ROLE_CODE,
    is_province_reader,
    normalize_role_code,
)
from app.survey_models import SurveyPerson, SurveyPersonYearRecord


APP_DIR = Path(__file__).resolve().parent
TEMPLATE_ROOT = APP_DIR / "report_templates" / "pcgd_xmc_2025"

REPORT_TEMPLATE_FILES = {
    "PCGD_TH_02_2025": "PCGD_2025_TH_02.xlsx",
    "PCGD_TH_01_GV_2025": "PCGD_2025_TH_01_GV.xlsx",
    "PCGD_TH_01_CSVC_2025": "PCGD_2025_TH_01_CSVC.xlsx",
    "PCGD_THCS_M1_2025": "PCGD_2025_THCS_M1.xlsx",
    "PCGD_THCS_M2_2025": "PCGD_2025_THCS_M2.xlsx",
    "PCGD_THCS_TK_2025": "PCGD_2025_THCS_TK.xlsx",
    "PCGD_THCS_M5_2025": "PCGD_2025_THCS_M5.xlsx",
    "PCGD_THCS_CSVC_2025": "PCGD_2025_THCS_CSVC.xlsx",
    "PCGD_XMC_3_2025": "PCGD_2025_XMC_3.xlsx",
    "PCGD_CMC_2_2025": "PCGD_2025_CMC_2.xlsx",
    "PCGD_CMC_1_2025": "PCGD_2025_CMC_1.xlsx",
    "PCGD_XMC_4_2025": "PCGD_2025_XMC_4.xlsx",
}

SUPPORTED_REPORT_TYPES = frozenset(REPORT_TEMPLATE_FILES)
LOWER_SCOPE_REPORT_VERSION = "PCGD-XMC-REPORT-LOWER-SCOPES-V1.4"


def _norm(value: Any) -> str:
    text = str(value or "").strip().upper().replace("_", " ")
    text = text.replace("Đ", "D")
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return " ".join(text.split())


def _reference_year(school_year: SchoolYear | None) -> int:
    if school_year is not None:
        match = re.search(r"(20\d{2})", str(school_year.code or ""))
        if match:
            return int(match.group(1))
    return datetime.now().year


def _safe_filename_text(value: Any) -> str:
    text = _norm(value)
    text = re.sub(r"[^A-Z0-9]+", "_", text).strip("_")
    return text or "TOAN_TINH"


def _clean_scope_label(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _school_scope_label(name: Any) -> str:
    text = _clean_scope_label(name)
    if not text:
        return "Trường"
    return text if _norm(text).startswith("TRUONG ") else f"Trường {text}"


def _effective_scope_for_user(
    *,
    db: Session,
    request: Any,
    selected_commune_id: int | None,
    selected_school_id: int | None,
    scope_label: str,
) -> tuple[int | None, int | None, str, str]:
    """
    Cố định phạm vi xuất theo tài khoản mà không thay đổi route/luồng cũ.

    - Sở/Phòng ban: giữ phạm vi đã được report_center kiểm tra.
    - Xã/phường: luôn giới hạn trong xã của tài khoản; vẫn cho phép chọn
      một trường thuộc đúng xã nếu giao diện hiện tại đã cho chọn.
    - Trường/Giáo viên: luôn khóa về đúng trường của tài khoản.

    Hàm chỉ đọc auth_user và danh mục; không ghi cơ sở dữ liệu.
    """
    user = getattr(request, "scope", {}).get("auth_user") or {}
    role_code = normalize_role_code(user.get("role_code"))
    account_commune_id = user.get("commune_id")
    account_school_id = user.get("school_id")

    try:
        account_commune_id = int(account_commune_id) if account_commune_id is not None else None
    except (TypeError, ValueError):
        account_commune_id = None
    try:
        account_school_id = int(account_school_id) if account_school_id is not None else None
    except (TypeError, ValueError):
        account_school_id = None

    if is_province_reader(role_code):
        return (
            selected_commune_id,
            selected_school_id,
            _clean_scope_label(scope_label) or "Toàn tỉnh",
            "province",
        )

    if role_code == COMMUNE_ROLE_CODE:
        commune = db.get(Commune, account_commune_id) if account_commune_id else None
        effective_commune_id = int(commune.id) if commune is not None else account_commune_id
        effective_school_id: int | None = None
        if selected_school_id is not None:
            school = db.get(School, int(selected_school_id))
            if (
                school is not None
                and school.is_active
                and effective_commune_id is not None
                and int(school.commune_id) == int(effective_commune_id)
            ):
                effective_school_id = int(school.id)
        if effective_school_id is not None:
            school = db.get(School, effective_school_id)
            label = _school_scope_label(school.name) if school is not None else _clean_scope_label(scope_label)
        else:
            label = commune.name if commune is not None else (_clean_scope_label(scope_label) or "Cấp xã/phường")
        return effective_commune_id, effective_school_id, label, "commune"

    if role_code in {SCHOOL_ROLE_CODE, TEACHER_ROLE_CODE}:
        school = db.get(School, account_school_id) if account_school_id else None
        if school is None:
            return account_commune_id, account_school_id, (_clean_scope_label(scope_label) or str(user.get("unit_name") or "Phạm vi tài khoản")), "school"
        return (
            int(school.commune_id) if school.commune_id is not None else account_commune_id,
            int(school.id),
            _school_scope_label(school.name),
            "school",
        )

    # Vai trò khác: không nới phạm vi ngoài giá trị đã được router kiểm tra.
    return selected_commune_id, selected_school_id, (_clean_scope_label(scope_label) or "Phạm vi tài khoản"), "account"


def _scope_meta(
    *,
    scope_label: str,
    selected_commune_id: int | None,
    selected_school_id: int | None,
    year: int,
) -> dict[str, str]:
    raw = str(scope_label or "").strip() or "Toàn tỉnh"
    province = selected_commune_id is None and selected_school_id is None
    school = selected_school_id is not None
    if province:
        return {
            "title": "Toàn tỉnh",
            "place": "Nghệ An",
            "signature": "XÁC NHẬN CỦA SỞ GIÁO DỤC VÀ ĐÀO TẠO",
            "signer": "GIÁM ĐỐC",
            "year": str(year),
            "kind": "province",
        }
    if school:
        return {
            "title": raw,
            "place": raw,
            "signature": "XÁC NHẬN CỦA NHÀ TRƯỜNG",
            "signer": "HIỆU TRƯỞNG",
            "year": str(year),
            "kind": "school",
        }
    return {
        "title": raw,
        "place": raw,
        "signature": "XÁC NHẬN CỦA UBND XÃ/PHƯỜNG",
        "signer": "PHÓ CHỦ TỊCH",
        "year": str(year),
        "kind": "commune",
    }


def _age(person: SurveyPerson, year: int) -> int | None:
    if person.date_of_birth is None:
        return None
    return year - int(person.date_of_birth.year)


def _female(person: SurveyPerson) -> bool:
    return _norm(person.gender) in {"NU", "F", "FEMALE", "GIRL"}


def _ethnic(person: SurveyPerson) -> bool:
    value = _norm(person.ethnic_group)
    return bool(value) and value not in {"KINH", "K"}


def _female_ethnic(person: SurveyPerson) -> bool:
    return _female(person) and _ethnic(person)


def _grade(record: SurveyPersonYearRecord | None) -> int | None:
    if record is None:
        return None
    name = ""
    if record.classroom is not None:
        name = str(record.classroom.name or "")
    if not name:
        name = str(record.class_name_reported or "")
    text = _norm(name)
    match = re.search(r"(?<!\d)(1[0-2]|[1-9])(?=[A-Z]|\b|\s|/|\-|$)", text)
    if not match:
        return None
    value = int(match.group(1))
    return value if 1 <= value <= 12 else None


def _status(record: SurveyPersonYearRecord | None) -> str:
    return _norm(record.learning_status if record is not None else "")


def _is_disabled(person: SurveyPerson, record: SurveyPersonYearRecord | None) -> bool:
    if record is not None and _norm(record.disability_status) in {"CO KHUYET TAT", "CO_KHUYET_TAT"}:
        return True
    student = getattr(person, "student", None)
    return bool(student is not None and str(getattr(student, "disability_type", "") or "").strip())


def _disabled_access(person: SurveyPerson, record: SurveyPersonYearRecord | None) -> bool:
    if not _is_disabled(person, record):
        return False
    return _status(record) in {"DANG HOC", "DANG_HOC", "CHUYEN DEN", "CHUYEN_DEN", "CHUYEN DI", "CHUYEN_DI", "DA TOT NGHIEP", "DA_TOT_NGHIEP"}


def _completed_primary(person: SurveyPerson, record: SurveyPersonYearRecord | None) -> bool:
    if record is None:
        return False
    status = _status(record)
    if status in {"DA TOT NGHIEP", "DA_TOT_NGHIEP", "HOAN THANH", "HTCTTH"}:
        return True
    grade = _grade(record)
    if grade is not None and grade >= 6:
        return True
    note = _norm(" ".join([str(record.notes or ""), str(person.notes or ""), str(person.special_circumstances or "")]))
    return "HOAN THANH CHUONG TRINH TIEU HOC" in note or "HTCTTH" in note


def _completed_secondary(person: SurveyPerson, record: SurveyPersonYearRecord | None) -> bool:
    if record is None:
        return False
    status = _status(record)
    if status in {"TN THCS", "TN_THCS", "TOT NGHIEP THCS", "DA TOT NGHIEP THCS", "DA_TOT_NGHIEP_THCS"}:
        return True
    grade = _grade(record)
    if grade is not None and grade >= 10:
        return True
    note = _norm(" ".join([str(record.notes or ""), str(person.notes or ""), str(person.special_circumstances or "")]))
    return "TOT NGHIEP THCS" in note or "TNTHCS" in note


def _upper_secondary(person: SurveyPerson, record: SurveyPersonYearRecord | None) -> bool:
    if record is None:
        return False
    grade = _grade(record)
    status = _status(record)
    if status in {"BO HOC", "BO_HOC", "THOI HOC", "THOI_HOC", "CHUA DI HOC", "CHUA_DI_HOC"}:
        return False
    if grade is not None and grade >= 10:
        return True
    text = _norm(" ".join([str(record.school_name_reported or ""), str(record.notes or "")]))
    return any(token in text for token in ("THPT", "GDTX", "GDNN", "TRUNG HOC PHO THONG"))


def _is_ppc(person: SurveyPerson, record: SurveyPersonYearRecord | None) -> bool:
    if _norm(person.residency_status) not in {"THUONG TRU", "THUONG_TRU"}:
        return False
    return _status(record) not in {"KHONG THUOC DIEN", "KHONG_THUOC_DIEN"}


def _location_bucket(person: SurveyPerson, record: SurveyPersonYearRecord | None, reporting_commune_id: int | None) -> str:
    home_commune_id = None
    household = getattr(person, "household", None)
    if household is not None and getattr(household, "commune_id", None) is not None:
        home_commune_id = int(household.commune_id)
    school_commune_id = None
    if record is not None and record.school is not None and record.school.commune_id is not None:
        school_commune_id = int(record.school.commune_id)
    if reporting_commune_id is None:
        if record is not None and record.school_id is None and str(record.school_name_reported or "").strip():
            return "other"
        return "local"
    if home_commune_id == reporting_commune_id:
        if school_commune_id is None:
            return "other" if record is not None and str(record.school_name_reported or "").strip() else "local"
        return "local" if school_commune_id == reporting_commune_id else "other"
    if school_commune_id == reporting_commune_id:
        return "inbound"
    return "other"


def _percent(numerator: int | float, denominator: int | float) -> float | None:
    if not denominator:
        return None
    return round(float(numerator) * 100.0 / float(denominator), 2)


def _load_people_and_records(
    *, db: Session, request: Any, school_year_id: int, selected_commune_id: int | None, selected_school_id: int | None
) -> list[tuple[SurveyPerson, SurveyPersonYearRecord | None]]:
    from app.routers import report_center as rc
    return rc._th_m1_load_people_and_records(
        db=db,
        request=request,
        school_year_id=school_year_id,
        selected_commune_id=selected_commune_id,
        selected_school_id=selected_school_id,
    )


def _population_metrics(people_and_records: list[tuple[SurveyPerson, SurveyPersonYearRecord | None]], year: int) -> dict[int, dict[str, int]]:
    metrics: dict[int, dict[str, int]] = defaultdict(lambda: {"total": 0, "female": 0, "ethnic": 0, "female_ethnic": 0, "disabled": 0, "disabled_access": 0, "ppc": 0})
    for person, record in people_and_records:
        age = _age(person, year)
        if age is None:
            continue
        item = metrics[age]
        item["total"] += 1
        item["female"] += int(_female(person))
        item["ethnic"] += int(_ethnic(person))
        item["female_ethnic"] += int(_female_ethnic(person))
        item["disabled"] += int(_is_disabled(person, record))
        item["disabled_access"] += int(_disabled_access(person, record))
        item["ppc"] += int(_is_ppc(person, record))
    return metrics


def _sum_metric(metrics: dict[int, dict[str, int]], ages: range | list[int] | tuple[int, ...], key: str) -> int:
    return sum(int(metrics.get(age, {}).get(key, 0)) for age in ages)


def _write_scope_signature(ws: Any, report_type: str, meta: dict[str, str]) -> None:
    year = meta["year"]
    title = meta["title"]
    place = meta["place"]
    sig = meta["signature"]
    signer = meta["signer"]
    province = meta["kind"] == "province"
    mappings = {
        "PCGD_TH_02_2025": ("A2", "K10", "K11", "K12", ("A18", "K18")),
        "PCGD_TH_01_GV_2025": ("A2", "O25", "O26", "O27", ("B33", "O33")),
        "PCGD_TH_01_CSVC_2025": ("A2", "T20", "T21", "T22", ("C27", "T27")),
        "PCGD_THCS_M1_2025": ("A2", "M43", "M44", "M45", ("D51", "M51")),
        "PCGD_THCS_M2_2025": ("A3", "K27", "K28", "K29", ("A35", "K35")),
        "PCGD_THCS_TK_2025": ("A2", "K10", "K11", "K12", ("A18", "K18")),
        "PCGD_THCS_M5_2025": ("A3", "AB25", "AB26", "AB27", ("F33", "AB33")),
        "PCGD_THCS_CSVC_2025": ("A3", "K20", "K21", "K22", ("A28", "K28")),
        "PCGD_XMC_3_2025": ("A2", "H59", "H60", "H61", ("A67", "H67")),
        "PCGD_CMC_2_2025": ("A2", "K13", "K14", "K15", ("A21", "K21")),
        "PCGD_CMC_1_2025": ("A2", "X11", "X12", "X13", ("C19", "X19")),
        "PCGD_XMC_4_2025": ("A2", "K10", "K11", "K12", ("A18", "K18")),
    }
    loc_cell, date_cell, sig_cell, signer_cell, clear_cells = mappings[report_type]
    if report_type == "PCGD_CMC_2_2025":
        ws[loc_cell] = f"{title}, Tỉnh: Nghệ An" if not province else "Toàn tỉnh, Tỉnh: Nghệ An"
    elif report_type == "PCGD_CMC_1_2025":
        ws[loc_cell] = f"{title}, tỉnh Nghệ An" if not province else "Toàn tỉnh, tỉnh Nghệ An"
    elif report_type in {"PCGD_THCS_M1_2025", "PCGD_THCS_M2_2025", "PCGD_THCS_M5_2025", "PCGD_THCS_CSVC_2025", "PCGD_XMC_3_2025", "PCGD_XMC_4_2025"}:
        ws[loc_cell] = title if province else title
    else:
        ws[loc_cell] = title
    ws[date_cell] = f"{place}, ngày      tháng      năm {year}"
    ws[sig_cell] = sig
    ws[signer_cell] = signer
    for ref in clear_cells:
        ws[ref] = None


def _schools_and_classes(db: Session, school_year_id: int, selected_commune_id: int | None, selected_school_id: int | None) -> tuple[list[School], dict[int, list[int]]]:
    stmt = select(School).where(School.is_active.is_(True)).order_by(School.name.asc())
    if selected_school_id is not None:
        stmt = stmt.where(School.id == selected_school_id)
    elif selected_commune_id is not None:
        stmt = stmt.where(School.commune_id == selected_commune_id)
    schools = list(db.scalars(stmt).all())
    if not schools:
        return [], {}
    class_stmt = select(Classroom).where(Classroom.school_year_id == school_year_id, Classroom.school_id.in_([s.id for s in schools]), Classroom.is_active.is_(True))
    classes = list(db.scalars(class_stmt).all())
    grades: dict[int, list[int]] = defaultdict(list)
    for item in classes:
        text = _norm(item.name)
        m = re.search(r"(?<!\d)(1[0-2]|[1-9])(?=[A-Z]|\b|\s|/|\-|$)", text)
        if m:
            grades[int(item.school_id)].append(int(m.group(1)))
    return schools, grades


def _school_level(school: School, grades: dict[int, list[int]]) -> str | None:
    name = _norm(school.name)
    g = grades.get(int(school.id), [])
    if any(6 <= x <= 9 for x in g) or "THCS" in name or "TRUNG HOC CO SO" in name:
        return "THCS"
    if any(1 <= x <= 5 for x in g) or "TIEU HOC" in name or re.search(r"(^| )TH( |$)", name):
        return "TH"
    return None


# === BAI_13B_6_V1_2_NETWORK_EXPORT_START ===
def _network_year_start(code: str | None) -> int:
    try:
        return int(str(code or "").split("-", 1)[0])
    except (TypeError, ValueError):
        return 0


def _network_level_school_ids(db: Session, level: str) -> set[int]:
    return {
        int(value)
        for value in db.scalars(
            select(SchoolNetworkYearData.school_id)
            .where(SchoolNetworkYearData.level_code == level)
            .distinct()
        ).all()
    }


def _network_reference_data(
    db: Session,
    *,
    school_id: int,
    level: str,
    target_year_id: int,
) -> dict[str, Any]:
    rows = list(
        db.scalars(
            select(SchoolNetworkYearData)
            .where(
                SchoolNetworkYearData.school_id == school_id,
                SchoolNetworkYearData.level_code == level,
            )
            .options(selectinload(SchoolNetworkYearData.school_year))
        ).all()
    )
    if not rows:
        return {}
    target_year = db.get(SchoolYear, target_year_id)
    target_start = _network_year_start(getattr(target_year, "code", None))

    def key(item: SchoolNetworkYearData) -> tuple[int, int]:
        start = _network_year_start(getattr(item.school_year, "code", None))
        return (1 if (not target_start or start <= target_start) else 0, start)

    item = max(rows, key=key)
    try:
        data = json.loads(item.data_json or "{}")
    except Exception:
        data = {}
    return data if isinstance(data, dict) else {}


def _school_supports_report_level(
    db: Session,
    school: School,
    grades: dict[int, list[int]],
    level: str,
) -> bool:
    if int(school.id) in _network_level_school_ids(db, level):
        return True
    return _school_level(school, grades) == level


def _class_count_with_network(
    db: Session,
    *,
    school_id: int,
    school_year_id: int,
    grades: dict[int, list[int]],
    level: str,
) -> int:
    current = _class_count(grades.get(int(school_id), []), level)
    if current:
        return current
    data = _network_reference_data(
        db,
        school_id=school_id,
        level=level,
        target_year_id=school_year_id,
    )
    try:
        return max(0, int(float(data.get("class_total") or 0)))
    except (TypeError, ValueError):
        return 0
# === BAI_13B_6_V1_2_NETWORK_EXPORT_END ===


def _staff_rows(db: Session, school_year_id: int, school_ids: list[int]) -> dict[int, list[StaffYearRecord]]:
    if not school_ids:
        return {}
    stmt = (
        select(StaffYearRecord)
        .where(StaffYearRecord.school_year_id == school_year_id, StaffYearRecord.school_id.in_(school_ids), StaffYearRecord.is_active.is_(True))
        .options(selectinload(StaffYearRecord.staff_member))
    )
    result: dict[int, list[StaffYearRecord]] = defaultdict(list)
    for row in db.scalars(stmt).all():
        result[int(row.school_id)].append(row)
    return result


def _class_count(grades: list[int], level: str) -> int:
    if level == "TH":
        return sum(1 for x in grades if 1 <= x <= 5)
    return sum(1 for x in grades if 6 <= x <= 9)


def _staff_summary(records: list[StaffYearRecord], class_count: int) -> dict[str, Any]:
    teachers = [r for r in records if _norm(r.position_group) == "GIAO VIEN"]
    managers = [r for r in records if _norm(r.position_group) == "CBQL"]
    employees = [r for r in records if _norm(r.position_group) == "NHAN VIEN"]
    def member(r: StaffYearRecord) -> StaffMember | None:
        return getattr(r, "staff_member", None)
    principal = sum(1 for r in managers if "HIEU TRUONG" in _norm(r.position_title) and "PHO" not in _norm(r.position_title))
    vice = sum(1 for r in managers if "PHO HIEU TRUONG" in _norm(r.position_title) or "P HIEU TRUONG" in _norm(r.position_title))
    female = sum(1 for r in teachers if member(r) is not None and _norm(member(r).gender) == "NU")
    ethnic = sum(
        1
        for r in teachers
        if member(r) is not None
        and bool(_norm(getattr(member(r), "ethnic_group", "")))
        and _norm(getattr(member(r), "ethnic_group", "")) != "KINH"
    )
    bienche = sum(1 for r in teachers if _norm(r.employment_type) == "BIEN CHE")
    hopdong = len(teachers) - bienche
    qual = defaultdict(int)
    prof = defaultdict(int)
    subjects = defaultdict(int)
    emp_roles = defaultdict(int)
    for r in teachers:
        q = _norm(r.qualification_level)
        if q in {"THAC SI", "TIEN SI"}:
            qual["postgrad"] += 1
        elif q == "DAI HOC":
            qual["univ"] += 1
        elif q == "CAO DANG":
            qual["college"] += 1
        elif q == "TRUNG CAP":
            qual["secondary"] += 1
        ps = _norm(r.professional_standard)
        if ps == "TOT": prof["excellent"] += 1
        elif ps == "KHA": prof["good"] += 1
        elif ps == "DAT": prof["average"] += 1
        elif ps == "CHUA DAT": prof["poor"] += 1
        text = _norm(" ".join([
            str(getattr(r, "teaching_subject", "") or ""),
            str(getattr(r, "main_specialty", "") or ""),
            str(r.position_title or ""),
            str(r.notes or ""),
        ]))
        mapping = {
            "TOAN": "math", "NGU VAN": "literature", "VAN": "literature", "VAT LY": "physics", "LY": "physics", "HOA HOC": "chemistry", "HOA": "chemistry", "SINH HOC": "biology", "SINH": "biology", "LICH SU": "history", "SU": "history", "DIA LY": "geography", "DIA": "geography", "NHAC": "music", "AM NHAC": "music", "MY THUAT": "art", "MT": "art", "GIAO DUC THE CHAT": "pe", "THE DUC": "pe", "TD": "pe", "GIAO DUC CONG DAN": "civic", "GDCD": "civic", "CONG NGHE": "technology", "TIN HOC": "it", "TIN": "it", "TIENG ANH": "english", "ANH": "english", "TIENG NGA": "russian", "TIENG PHAP": "french", "NGOAI NGU": "foreign",
        }
        matched = False
        for token, key in mapping.items():
            if re.search(rf"(^| )({re.escape(token)})( |$)", text):
                subjects[key] += 1
                matched = True
                break
        if not matched:
            subjects["general"] += 1
    for r in employees:
        text = _norm(" ".join([str(r.position_title or ""), str(r.notes or "")]))
        if "THU VIEN" in text: emp_roles["library"] += 1
        elif "THIET BI" in text or "THI NGHIEM" in text: emp_roles["equipment"] += 1
        elif "Y TE" in text: emp_roles["health"] += 1
        elif "VAN PHONG" in text or "VAN THU" in text: emp_roles["office"] += 1
        else: emp_roles["other"] += 1
    return {
        "principal": principal, "vice": vice, "teachers": len(teachers), "bienche": bienche, "hopdong": hopdong,
        "female": female, "ethnic": ethnic, "ratio": round(len(teachers) / class_count, 2) if class_count else None,
        "qual": qual, "prof": prof, "subjects": subjects, "employees": emp_roles,
    }


def _clear_range(ws: Any, min_row: int, max_row: int, min_col: int, max_col: int) -> None:
    for row in ws.iter_rows(min_row=min_row, max_row=max_row, min_col=min_col, max_col=max_col):
        for cell in row:
            if cell.__class__.__name__ == "MergedCell":
                continue
            cell.value = None



# === BAI_13B_11_15_2_4_5_1_DISABLED_CAPABLE_AND_M2_CLEANUP ===
def _b152451_disabled_can_learn(
    person: SurveyPerson,
    record: SurveyPersonYearRecord | None,
) -> bool:
    """
    Bài 13B-11.15.2.4.5.2 V2 - tương thích dữ liệu cũ.

    Ưu tiên dữ liệu tường minh:
    - True  -> Có khả năng học.
    - False -> Không có khả năng học.
    - None + disability_access_education=True
      -> suy ra Có CHỈ KHI LẬP BÁO CÁO.

    Không ghi giá trị suy ra trở lại database.
    """
    if (
        not _is_disabled(person, record)
        or record is None
    ):
        return False

    explicit = getattr(
        record,
        "disability_can_learn",
        None,
    )

    if explicit is True:
        return True

    if explicit is False:
        return False

    return (
        getattr(
            record,
            "disability_access_education",
            None,
        )
        is True
    )

# === BAI_13B_11_15_2_4_5_2_V2_DISABILITY_LEGACY_COMPAT ===
def _b152451_disabled_access(
    person: SurveyPerson,
    record: SurveyPersonYearRecord | None,
) -> bool:
    # Tử số tiếp cận GD chỉ thuộc nhóm có khả năng học tập.
    return bool(
        _b152451_disabled_can_learn(
            person,
            record,
        )
        and record is not None
        and getattr(
            record,
            "disability_access_education",
            None,
        )
        is True
    )


def _b152451_plain_number(
    value: float | int | None,
) -> str:
    if value is None:
        return ""

    number = float(value)

    if number.is_integer():
        return str(
            int(number)
        )

    return (
        f"{number:.2f}"
        .rstrip("0")
        .rstrip(".")
    )


def _b152451_looks_like_sample_ratio(
    value: object,
) -> bool:
    if not isinstance(
        value,
        str,
    ):
        return False

    text = value.strip()

    if text.count("/") != 1:
        return False

    left, right = (
        part.strip()
        for part in text.split(
            "/",
            1,
        )
    )

    def is_number(
        item: str,
    ) -> bool:
        compact = (
            item.replace(
                ".",
                "",
            )
            .replace(
                ",",
                "",
            )
            .replace(
                " ",
                "",
            )
        )

        return bool(
            compact
            and compact.isdigit()
        )

    return (
        is_number(left)
        and is_number(right)
    )


def _b152451_ratio_text(
    ws: Any,
    numerator_refs: tuple[str, ...],
    denominator_refs: tuple[str, ...],
) -> str:
    numerator = _b15245_ws_sum(
        ws,
        numerator_refs,
    )

    denominator = _b15245_ws_sum(
        ws,
        denominator_refs,
    )

    if (
        numerator is None
        or denominator is None
    ):
        return ""

    return (
        _b152451_plain_number(
            numerator
        )
        + "/"
        + _b152451_plain_number(
            denominator
        )
    )


def _b152451_clean_thcs_m2_evaluation(
    ws: Any,
) -> None:
    # K20:K24 lấy tỷ lệ thực tế từ dòng Tổng 15.
    result_map = {
        20: "E15",
        21: "M15",
        22: "J15",
        23: "Q15",
        24: "V15",
    }

    # Tỉ số thực tế tương ứng 5 tiêu chí.
    ratio_map = {
        20: (
            ("D15",),
            ("C15",),
        ),
        21: (
            ("L15",),
            ("K15",),
        ),
        22: (
            ("I15",),
            ("F15",),
        ),
        23: (
            ("P15", "O15"),
            ("N15",),
        ),
        24: (
            ("U15",),
            ("R15",),
        ),
    }

    for row, source_ref in result_map.items():
        ws[f"K{row}"] = _b15245_ws_number(
            ws,
            source_ref,
        )

    for row, (
        numerator_refs,
        denominator_refs,
    ) in ratio_map.items():
        actual_ratio = _b152451_ratio_text(
            ws,
            numerator_refs,
            denominator_refs,
        )

        # Chỉ thay chuỗi minh họa dạng số/số trong đúng dòng 20-24.
        for column in range(
            1,
            ws.max_column + 1,
        ):
            cell = ws.cell(
                row,
                column,
            )

            if _b152451_looks_like_sample_ratio(
                cell.value
            ):
                cell.value = (
                    actual_ratio
                    or None
                )
                break

    # Bỏ ghi chú đỏ "Số liệu trong bảng là số liệu làm mẫu"
    # dù mẫu có dịch chuyển ô.
    for row_cells in ws.iter_rows():
        for cell in row_cells:
            if not isinstance(
                cell.value,
                str,
            ):
                continue

            normalized = _norm(
                cell.value
            )

            if (
                "SO LIEU TRONG BANG"
                in normalized
                and "LAM MAU"
                in normalized
            ):
                cell.value = None
# === END BAI_13B_11_15_2_4_5_1_DISABLED_CAPABLE_AND_M2_CLEANUP ===


def _build_th02(ws: Any, people: list[tuple[SurveyPerson, SurveyPersonYearRecord | None]], year: int, meta: dict[str, str], school_count: int) -> None:
    _clear_range(ws, 8, 8, 1, 20)
    age6 = [pr for pr in people if _age(pr[0], year) == 6]
    age11 = [pr for pr in people if _age(pr[0], year) == 11]
    age11_14 = [pr for pr in people if (_age(pr[0], year) or -1) in range(11, 15)]
    students = [pr for pr in people if (_grade(pr[1]) or 0) in range(1, 6) and _status(pr[1]) not in {"BO HOC", "THOI HOC", "CHUA DI HOC"}]
    disabled_students = sum(1 for p, r in students if _is_disabled(p, r))
    ppc6 = sum(1 for p, r in age6 if _is_ppc(p, r))
    grade1_age6 = sum(1 for p, r in age6 if _is_ppc(p, r) and _grade(r) == 1)
    ppc11 = sum(1 for p, r in age11 if _is_ppc(p, r))
    comp11 = sum(1 for p, r in age11 if _is_ppc(p, r) and _completed_primary(p, r))
    ppc1114 = sum(1 for p, r in age11_14 if _is_ppc(p, r))
    comp1114 = sum(1 for p, r in age11_14 if _is_ppc(p, r) and _completed_primary(p, r))
    disabled = sum(1 for p, r in people if 6 <= (_age(p, year) or -1) <= 14 and _is_disabled(p, r))
    disabled_capable = sum(
        1
        for p, r in people
        if 6 <= (_age(p, year) or -1) <= 14
        and _b152451_disabled_can_learn(p, r)
    )
    disabled_access = sum(
        1
        for p, r in people
        if 6 <= (_age(p, year) or -1) <= 14
        and _b152451_disabled_access(p, r)
    )
    row = 8
    values = {1: 1, 2: meta["title"], 3: 1 if meta["kind"] != "province" else None, 4: school_count, 6: len(students), 7: disabled_students, 8: grade1_age6, 9: _percent(grade1_age6, ppc6), 10: comp11, 11: _percent(comp11, ppc11), 12: comp1114, 13: _percent(comp1114, ppc1114), 14: disabled, 15: disabled_capable, 16: disabled_access, 17: _percent(disabled_access, disabled_capable)}
    for col, value in values.items(): ws.cell(row, col).value = value



def _build_thcs_m1(ws: Any, people: list[tuple[SurveyPerson, SurveyPersonYearRecord | None]], year: int, meta: dict[str, str], commune_id: int | None) -> None:
    age_cols = {11: 6, 12: 8, 13: 10, 14: 12, 15: 14, 16: 17, 17: 20, 18: 23}
    for row in list(range(6, 13)) + list(range(14, 35)):
        for col in range(6, 27):
            if row == 13:
                continue
            cell = ws.cell(row, col)
            if cell.__class__.__name__ == "MergedCell":
                continue
            cell.value = None
    by_age = defaultdict(list)
    for p, r in people:
        age = _age(p, year)
        if age in age_cols: by_age[age].append((p, r))
    for age, col in age_cols.items():
        group = by_age[age]
        ws.cell(4, col).value = year - age
        ws.cell(6, col).value = len(group) or None
        ws.cell(7, col).value = sum(1 for p, r in group if _female(p)) or None
        ws.cell(8, col).value = sum(1 for p, r in group if _ethnic(p)) or None
        ws.cell(9, col).value = sum(1 for p, r in group if _is_disabled(p, r)) or None
        ws.cell(10, col).value = sum(
            1
            for p, r in group
            if _b152451_disabled_can_learn(p, r)
        ) or None
        ws.cell(11, col).value = sum(
            1
            for p, r in group
            if _b152451_disabled_access(p, r)
        ) or None
        ws.cell(12, col).value = sum(1 for p, r in group if _is_ppc(p, r)) or None
    for row_start, grade in ((14,6),(17,7),(20,8),(23,9)):
        for p, r in people:
            age = _age(p, year)
            if age not in age_cols or _grade(r) != grade or not _is_ppc(p, r): continue
            bucket = _location_bucket(p, r, commune_id)
            rr = row_start + {"local":0,"other":1,"inbound":2}[bucket]
            col = age_cols[age]
            ws.cell(rr, col).value = int(ws.cell(rr, col).value or 0) + 1
    for p, r in people:
        age = _age(p, year)
        if age not in age_cols: continue
        col = age_cols[age]
        bucket = _location_bucket(p, r, commune_id)
        off = {"local":0,"other":1,"inbound":2}[bucket]
        if _completed_secondary(p, r):
            rr = 26 + off; ws.cell(rr,col).value = int(ws.cell(rr,col).value or 0)+1
        if _upper_secondary(p, r):
            rr = 29 + off; ws.cell(rr,col).value = int(ws.cell(rr,col).value or 0)+1
        if _is_ppc(p, r) and _status(r) in {"BO HOC","BO_HOC","THOI HOC","THOI_HOC"}:
            rr = 32 + off; ws.cell(rr,col).value = int(ws.cell(rr,col).value or 0)+1
    for row in range(6,35):
        if row == 13: continue
        ws.cell(row,26).value = sum(int(ws.cell(row,c).value or 0) for c in (14,17,20,23)) or None
    age15_18 = [(p,r) for p,r in people if (_age(p,year) or -1) in range(15,19) and _is_ppc(p,r)]
    sec = sum(1 for p,r in age15_18 if _completed_secondary(p,r))
    upper = sum(1 for p,r in age15_18 if _upper_secondary(p,r))
    disabled = sum(1 for p,r in age15_18 if _is_disabled(p,r))
    capable = sum(
        1 for p,r in age15_18
        if _b152451_disabled_can_learn(p,r)
    )
    access = sum(
        1 for p,r in age15_18
        if _b152451_disabled_access(p,r)
    )
    ws["G39"] = sec; ws["H39"] = _percent(sec, len(age15_18))
    ws["G40"] = upper; ws["H40"] = _percent(upper, len(age15_18))
    ws["G41"] = access; ws["H41"] = _percent(access, capable)
    ws["G42"] = sum(1 for p,r in people if (_grade(r) or 0) in range(6,10) and _status(r) not in {"BO HOC","THOI HOC","CHUA DI HOC"})
    ws["G36"] = None; ws["G37"] = None



def _build_thcs_m2(ws: Any, people: list[tuple[SurveyPerson, SurveyPersonYearRecord | None]], year: int, meta: dict[str,str]) -> None:
    _clear_range(ws, 14, 15, 1, 23)
    age6=[pr for pr in people if _age(pr[0],year)==6 and _is_ppc(*pr)]
    age11_14=[pr for pr in people if (_age(pr[0],year) or -1) in range(11,15) and _is_ppc(*pr)]
    age15_18=[pr for pr in people if (_age(pr[0],year) or -1) in range(15,19) and _is_ppc(*pr)]
    grade1=sum(1 for p,r in age6 if _grade(r)==1)
    htth=sum(1 for p,r in age11_14 if _completed_primary(p,r))
    tnthcs=sum(1 for p,r in age15_18 if _completed_secondary(p,r))
    row=14
    vals={1:1,2:meta["title"],3:len(age6),4:grade1,5:_percent(grade1,len(age6)),11:len(age11_14),12:htth,13:_percent(htth,len(age11_14)),18:len(age15_18),19:tnthcs,21:tnthcs,22:_percent(tnthcs,len(age15_18))}
    for c,v in vals.items(): ws.cell(row,c).value=v
    ws.cell(15,1).value="Tổng"
    for c in range(3,23): ws.cell(15,c).value=ws.cell(14,c).value
    for ref in ("P20","P21","P22","P23","P24","P25","W14"): ws[ref]=None


def _build_thcs_tk(ws: Any, people: list[tuple[SurveyPerson, SurveyPersonYearRecord | None]], year: int, meta: dict[str,str], school_count:int) -> None:
    _clear_range(ws,8,8,1,18)
    age1118=[pr for pr in people if (_age(pr[0],year) or -1) in range(11,19)]
    age1518=[pr for pr in age1118 if (_age(pr[0],year) or -1) in range(15,19) and _is_ppc(*pr)]
    disabled=[pr for pr in age1118 if _is_disabled(*pr)]
    capable=[
        pr for pr in disabled
        if _b152451_disabled_can_learn(*pr)
    ]
    tn=sum(1 for p,r in age1518 if _completed_secondary(p,r))
    upper=sum(1 for p,r in age1518 if _upper_secondary(p,r))
    access=sum(
        1 for p,r in capable
        if _b152451_disabled_access(p,r)
    )
    vals={1:1,2:meta["title"],3:school_count,4:len(age1118),5:sum(1 for p,r in age1118 if _is_disabled(p,r)),8:tn,9:_percent(tn,len(age1518)),10:upper,11:_percent(upper,len(age1518)),12:len(disabled),13:len(capable),14:access,15:_percent(access,len(capable))}
    for c,v in vals.items(): ws.cell(8,c).value=v



# === BAI_13B_11_15_2_4_7_XMC_FORMULA_CONTRACT ===
# === BAI_13B_11_15_2_4_7_1B_REPORT_SOURCE_START ===
def _xmc1471b_bool(
    record: SurveyPersonYearRecord | None,
    field_name: str,
) -> bool | None:
    if record is None:
        return None

    value = getattr(
        record,
        field_name,
        None,
    )

    if value is True:
        return True

    if value is False:
        return False

    if value == 1:
        return True

    if value == 0:
        return False

    text = str(
        value or ""
    ).strip().upper()

    if text in {
        "CO",
        "CÓ",
        "TRUE",
        "YES",
        "1",
    }:
        return True

    if text in {
        "KHONG",
        "KHÔNG",
        "FALSE",
        "NO",
        "0",
    }:
        return False

    return None


def _xmc1471b_metrics(
    people: list[
        tuple[
            SurveyPerson,
            SurveyPersonYearRecord | None,
        ]
    ],
    year: int,
) -> dict[int, dict[str, int]]:
    """
    Nguồn chuẩn cho 4 biểu XMC.

    Mọi người >=15 tuổi là đối tượng ĐIỀU TRA XMC.
    Không lọc bằng literacy_status.

    - MC mức 1 : completed_grade_3=False
    - BC mức 1 : completed_grade_3=True
    - MC mức 2 : completed_grade_5=False
    - BC mức 2 : completed_grade_5=True
    - None     : chưa phân loại, vẫn nằm trong dân số
    """
    keys = (
        "total",
        "female",
        "ethnic",
        "female_ethnic",
        "mc1_total",
        "mc1_female",
        "mc1_ethnic",
        "mc1_female_ethnic",
        "mc2_total",
        "mc2_female",
        "mc2_ethnic",
        "mc2_female_ethnic",
        "bc1_total",
        "bc1_female",
        "bc1_ethnic",
        "bc1_female_ethnic",
        "bc2_total",
        "bc2_female",
        "bc2_ethnic",
        "bc2_female_ethnic",
    )

    result: dict[
        int,
        dict[str, int],
    ] = {}

    for person, record in people:
        age = _age(
            person,
            year,
        )

        if age is None or age < 15:
            continue

        if age not in result:
            result[age] = {
                key: 0
                for key in keys
            }

        item = result[age]

        female = bool(
            _female(person)
        )

        ethnic = bool(
            _ethnic(person)
        )

        female_ethnic = bool(
            _female_ethnic(person)
        )

        item["total"] += 1
        item["female"] += int(female)
        item["ethnic"] += int(ethnic)
        item["female_ethnic"] += int(
            female_ethnic
        )

        grade3 = _xmc1471b_bool(
            record,
            "completed_grade_3",
        )

        grade5 = _xmc1471b_bool(
            record,
            "completed_grade_5",
        )

        if grade3 is False:
            item["mc1_total"] += 1
            item["mc1_female"] += int(
                female
            )
            item["mc1_ethnic"] += int(
                ethnic
            )
            item["mc1_female_ethnic"] += int(
                female_ethnic
            )

        elif grade3 is True:
            item["bc1_total"] += 1
            item["bc1_female"] += int(
                female
            )
            item["bc1_ethnic"] += int(
                ethnic
            )
            item["bc1_female_ethnic"] += int(
                female_ethnic
            )

        if grade5 is False:
            item["mc2_total"] += 1
            item["mc2_female"] += int(
                female
            )
            item["mc2_ethnic"] += int(
                ethnic
            )
            item["mc2_female_ethnic"] += int(
                female_ethnic
            )

        elif grade5 is True:
            item["bc2_total"] += 1
            item["bc2_female"] += int(
                female
            )
            item["bc2_ethnic"] += int(
                ethnic
            )
            item["bc2_female_ethnic"] += int(
                female_ethnic
            )

    return result


def _xmc1471b_sum(
    metrics: dict[int, dict[str, int]],
    ages,
    key: str,
) -> int:
    return sum(
        int(
            metrics
            .get(
                int(age),
                {},
            )
            .get(
                key,
                0,
            )
            or 0
        )
        for age in ages
    )


def _xmc1471b_value(
    population: int,
    value: int,
):
    if int(
        population or 0
    ) <= 0:
        return None

    return int(
        value or 0
    )
# === BAI_13B_11_15_2_4_7_1B_REPORT_SOURCE_END ===

def _build_xmc3(
    ws: Any,
    people: list[
        tuple[
            SurveyPerson,
            SurveyPersonYearRecord | None,
        ]
    ],
    year: int,
) -> None:
    row_by_age: dict[int, int] = {}

    for age in range(15, 26):
        row_by_age[age] = 9 + age - 15

    for age in range(26, 36):
        row_by_age[age] = 21 + age - 26

    for age in range(36, 61):
        row_by_age[age] = 32 + age - 36

    metrics = _xmc1471b_metrics(
        people,
        year,
    )

    column_keys = (
        (3, "total"),
        (4, "female"),
        (5, "ethnic"),
        (6, "female_ethnic"),
        (7, "mc1_total"),
        (8, "mc1_female"),
        (9, "mc1_ethnic"),
        (10, "mc1_female_ethnic"),
        (11, "mc2_total"),
        (12, "mc2_female"),
        (13, "mc2_ethnic"),
        (14, "mc2_female_ethnic"),
        (15, "bc2_total"),
        (16, "bc2_female"),
        (17, "bc2_ethnic"),
        (18, "bc2_female_ethnic"),
    )

    for age, row in row_by_age.items():
        item = metrics.get(
            age,
            {},
        )

        population = int(
            item.get(
                "total",
                0,
            )
            or 0
        )

        ws.cell(
            row,
            2,
        ).value = year - age

        for col, key in column_keys:
            value = int(
                item.get(
                    key,
                    0,
                )
                or 0
            )

            ws.cell(
                row,
                col,
            ).value = _xmc1471b_value(
                population,
                value,
            )

    for row, ages in (
        (20, range(15, 26)),
        (31, range(15, 36)),
        (57, range(15, 61)),
    ):
        ages = list(ages)

        population = _xmc1471b_sum(
            metrics,
            ages,
            "total",
        )

        for col, key in column_keys:
            value = _xmc1471b_sum(
                metrics,
                ages,
                key,
            )

            ws.cell(
                row,
                col,
            ).value = _xmc1471b_value(
                population,
                value,
            )

def _build_cmc2(
    ws: Any,
    people: list[
        tuple[
            SurveyPerson,
            SurveyPersonYearRecord | None,
        ]
    ],
    year: int,
) -> None:
    _clear_range(
        ws,
        8,
        11,
        2,
        19,
    )

    metrics = _xmc1471b_metrics(
        people,
        year,
    )

    groups = (
        (8, range(15, 26)),
        (9, range(26, 36)),
        (10, range(36, 61)),
        (11, range(15, 61)),
    )

    for row, ages in groups:
        ages = list(ages)

        population = _xmc1471b_sum(
            metrics,
            ages,
            "total",
        )

        assignments = {
            2: "total",
            3: "female",
            4: "ethnic",
            6: "mc1_total",
            7: "mc1_female",
            8: "mc1_ethnic",
            10: "mc2_total",
            11: "mc2_female",
            12: "mc2_ethnic",
        }

        for col, key in assignments.items():
            value = _xmc1471b_sum(
                metrics,
                ages,
                key,
            )

            ws.cell(
                row,
                col,
            ).value = _xmc1471b_value(
                population,
                value,
            )

        for col in (
            5,
            9,
            13,
            14,
            15,
            16,
            17,
            18,
            19,
        ):
            ws.cell(
                row,
                col,
            ).value = None

def _build_cmc1(
    ws: Any,
    people: list[
        tuple[
            SurveyPerson,
            SurveyPersonYearRecord | None,
        ]
    ],
    year: int,
    meta: dict[str, str],
) -> None:
    _clear_range(
        ws,
        8,
        8,
        3,
        66,
    )

    metrics = _xmc1471b_metrics(
        people,
        year,
    )

    all_people = [
        person
        for person, _record
        in people
    ]

    ws["A8"] = 1
    ws["B8"] = meta["title"]
    ws["C8"] = len(all_people)
    ws["D8"] = sum(
        int(_female(person))
        for person in all_people
    )
    ws["E8"] = sum(
        int(_ethnic(person))
        for person in all_people
    )
    ws["F8"] = sum(
        int(_female_ethnic(person))
        for person in all_people
    )

    groups = (
        (7, range(15, 26)),
        (27, range(15, 36)),
        (47, range(15, 61)),
    )

    demographic_keys = (
        "total",
        "female",
        "ethnic",
        "female_ethnic",
    )

    mc1_keys = (
        "mc1_total",
        "mc1_female",
        "mc1_ethnic",
        "mc1_female_ethnic",
    )

    mc2_keys = (
        "mc2_total",
        "mc2_female",
        "mc2_ethnic",
        "mc2_female_ethnic",
    )

    for start_col, ages in groups:
        ages = list(ages)

        population = _xmc1471b_sum(
            metrics,
            ages,
            "total",
        )

        for offset, key in enumerate(
            demographic_keys
        ):
            value = _xmc1471b_sum(
                metrics,
                ages,
                key,
            )

            ws.cell(
                8,
                start_col + offset,
            ).value = _xmc1471b_value(
                population,
                value,
            )

        for index, key in enumerate(
            mc1_keys
        ):
            value = _xmc1471b_sum(
                metrics,
                ages,
                key,
            )

            ws.cell(
                8,
                start_col + 4 + index * 2,
            ).value = _xmc1471b_value(
                population,
                value,
            )

        for index, key in enumerate(
            mc2_keys
        ):
            value = _xmc1471b_sum(
                metrics,
                ages,
                key,
            )

            ws.cell(
                8,
                start_col + 12 + index * 2,
            ).value = _xmc1471b_value(
                population,
                value,
            )

def _build_xmc4(
    ws: Any,
    people: list[
        tuple[
            SurveyPerson,
            SurveyPersonYearRecord | None,
        ]
    ],
    year: int,
    meta: dict[str, str],
) -> None:
    # === BAI_13B_11_15_2_4_7_1B_2_FIX_XMC4_LABEL_START ===
    # Chỉ sửa nhãn của biểu XMC-4 khi xuất Excel.
    for _b1471b2_row in ws.iter_rows():
        for _b1471b2_cell in _b1471b2_row:
            _b1471b2_value = str(
                getattr(_b1471b2_cell, "value", "") or ""
            ).strip()
            if _b1471b2_value == "Mẫu XMC-5":
                _b1471b2_cell.value = "Mẫu XMC-4"
    # === BAI_13B_11_15_2_4_7_1B_2_FIX_XMC4_LABEL_END ===

    _clear_range(
        ws,
        8,
        8,
        1,
        18,
    )

    metrics = _xmc1471b_metrics(
        people,
        year,
    )

    ws["A8"] = 1
    ws["B8"] = meta["title"]

    groups = (
        (3, range(15, 26)),
        (8, range(15, 36)),
        (13, range(15, 61)),
    )

    for total_col, ages in groups:
        ages = list(ages)

        population = _xmc1471b_sum(
            metrics,
            ages,
            "total",
        )

        bc1 = _xmc1471b_sum(
            metrics,
            ages,
            "bc1_total",
        )

        bc2 = _xmc1471b_sum(
            metrics,
            ages,
            "bc2_total",
        )

        ws.cell(
            8,
            total_col,
        ).value = _xmc1471b_value(
            population,
            population,
        )

        ws.cell(
            8,
            total_col + 1,
        ).value = _xmc1471b_value(
            population,
            bc1,
        )

        ws.cell(
            8,
            total_col + 3,
        ).value = _xmc1471b_value(
            population,
            bc2,
        )

    ws["R8"] = None

    # Các cột biết chữ mức độ 1/2 và mức đạt chuẩn để trống vì CSDL hiện chưa có trường chuyên biệt.


# === BAI_13B_6_V1_STRUCTURED_EXPORT_START ===

def _structured_input_rows(
    db: Session,
    *,
    school_year_id: int,
    school_ids: list[int],
    form_code: str,
) -> dict[int, dict[str, Any]]:
    if not school_ids:
        return {}
    stmt = select(SchoolStructuredReportInput).where(
        SchoolStructuredReportInput.school_year_id == school_year_id,
        SchoolStructuredReportInput.school_id.in_(school_ids),
        SchoolStructuredReportInput.form_code == form_code,
    )
    result: dict[int, dict[str, Any]] = {}
    for item in db.scalars(stmt).all():
        try:
            data = json.loads(item.data_json or "{}")
        except Exception:
            data = {}
        if isinstance(data, dict):
            result[int(item.school_id)] = data
    return result


def _structured_value(data: dict[str, Any], code: str) -> int | float | None:
    if code not in data or data[code] is None or data[code] == "":
        return None
    try:
        number = float(data[code])
    except (TypeError, ValueError):
        return None
    return int(number) if number.is_integer() else number


def _structured_overlay_export(
    *,
    ws: Any,
    db: Session,
    school_year_id: int,
    selected_commune_id: int | None,
    selected_school_id: int | None,
    level: str,
    form_code: str,
    start_row: int,
    total_row: int,
    max_rows: int,
    meta: dict[str, str],
    aggregate_if_province: bool,
) -> None:
    catalog = STRUCTURED_FORM_BY_CODE.get(form_code)
    if catalog is None:
        return

    schools, grades = _schools_and_classes(
        db,
        school_year_id,
        selected_commune_id,
        selected_school_id,
    )
    schools = [s for s in schools if _school_supports_report_level(db, s, grades, level)]
    if not schools:
        return

    school_ids = [int(s.id) for s in schools]
    records = _structured_input_rows(
        db,
        school_year_id=school_year_id,
        school_ids=school_ids,
        form_code=form_code,
    )
    if not records:
        return

    fields = [
        field
        for field in flatten_fields(catalog)
        if field.get("export", True)
        and int(field.get("excel_col") or 0) > 0
    ]
    field_map = {field["code"]: field for field in fields}
    number_fields = [field for field in fields if field["type"] != "yesno"]

    aggregate = len(schools) > max_rows or (
        aggregate_if_province and meta["kind"] == "province"
    )

    if aggregate:
        assignments = [(start_row, schools)]
    else:
        assignments = [
            (start_row + idx, [school])
            for idx, school in enumerate(schools)
        ]

    for row, row_schools in assignments:
        if len(row_schools) == 1:
            data = records.get(int(row_schools[0].id), {})
            for field in fields:
                value = _structured_value(data, field["code"])
                if value is None:
                    continue
                if field["type"] == "yesno":
                    ws.cell(row, field["excel_col"]).value = "x" if value else None
                else:
                    ws.cell(row, field["excel_col"]).value = value
        else:
            for field in number_fields:
                values = []
                for school in row_schools:
                    value = _structured_value(
                        records.get(int(school.id), {}),
                        field["code"],
                    )
                    if value is not None:
                        values.append(value)
                if values:
                    ws.cell(row, field["excel_col"]).value = sum(values)

        derived = catalog.get("derived") or {}
        ratio_col = int(derived.get("excel_col") or 0)
        if ratio_col:
            if derived.get("kind") == "staff_ratio":
                teachers_field = field_map.get("teacher_total")
                teachers = (
                    ws.cell(row, teachers_field["excel_col"]).value
                    if teachers_field else None
                )
                class_total = sum(
                    _class_count_with_network(
                        db,
                        school_id=int(s.id),
                        school_year_id=school_year_id,
                        grades=grades,
                        level=level,
                    )
                    for s in row_schools
                )
                try:
                    ws.cell(row, ratio_col).value = (
                        round(float(teachers) / class_total, 2)
                        if teachers is not None and class_total
                        else None
                    )
                except (TypeError, ValueError):
                    pass
            else:
                class_field = field_map.get("class_total")
                class_total = (
                    ws.cell(row, class_field["excel_col"]).value
                    if class_field else None
                )
                room_codes = [
                    "room_permanent",
                    "room_semi_permanent",
                    "room_temporary",
                ]
                if level == "TH":
                    room_codes.append("room_rent_borrow")
                room_total = 0.0
                for code in room_codes:
                    field = field_map.get(code)
                    if field is None:
                        continue
                    try:
                        room_total += float(
                            ws.cell(row, field["excel_col"]).value or 0
                        )
                    except (TypeError, ValueError):
                        pass
                try:
                    ws.cell(row, ratio_col).value = (
                        round(room_total / float(class_total), 2)
                        if class_total
                        else None
                    )
                except (TypeError, ValueError):
                    pass

    data_rows = [row for row, _items in assignments]
    for field in number_fields:
        col = int(field["excel_col"])
        values = []
        for row in data_rows:
            value = ws.cell(row, col).value
            if isinstance(value, (int, float)):
                values.append(value)
        if values:
            ws.cell(total_row, col).value = sum(values)

    derived = catalog.get("derived") or {}
    ratio_col = int(derived.get("excel_col") or 0)
    if ratio_col:
        if derived.get("kind") == "staff_ratio":
            teacher_field = field_map.get("teacher_total")
            teacher_total = 0.0
            if teacher_field is not None:
                for row in data_rows:
                    try:
                        teacher_total += float(
                            ws.cell(row, teacher_field["excel_col"]).value or 0
                        )
                    except (TypeError, ValueError):
                        pass
            class_total = sum(
                _class_count_with_network(
                    db,
                    school_id=int(s.id),
                    school_year_id=school_year_id,
                    grades=grades,
                    level=level,
                )
                for s in schools
            )
            if class_total:
                ws.cell(total_row, ratio_col).value = round(
                    teacher_total / class_total, 2
                )
        else:
            class_field = field_map.get("class_total")
            room_codes = [
                "room_permanent",
                "room_semi_permanent",
                "room_temporary",
            ]
            if level == "TH":
                room_codes.append("room_rent_borrow")

            class_total = 0.0
            room_total = 0.0
            if class_field is not None:
                try:
                    class_total = float(
                        ws.cell(total_row, class_field["excel_col"]).value or 0
                    )
                except (TypeError, ValueError):
                    class_total = 0

            for code in room_codes:
                field = field_map.get(code)
                if field is None:
                    continue
                try:
                    room_total += float(
                        ws.cell(total_row, field["excel_col"]).value or 0
                    )
                except (TypeError, ValueError):
                    pass

            if class_total:
                ws.cell(total_row, ratio_col).value = round(
                    room_total / class_total, 2
                )

# === BAI_13B_6_V1_STRUCTURED_EXPORT_END ===

def _write_staff_detail(ws: Any, report_type:str, db:Session, school_year_id:int, selected_commune_id:int|None, selected_school_id:int|None, level:str, meta:dict[str,str]) -> None:
    schools, grades=_schools_and_classes(db,school_year_id,selected_commune_id,selected_school_id)
    schools=[s for s in schools if _school_supports_report_level(db,s,grades,level)]
    records=_staff_rows(db,school_year_id,[int(s.id) for s in schools])
    if report_type=="PCGD_TH_01_GV_2025": start,total_row,max_rows=8,18,10
    else: start,total_row,max_rows=9,19,10
    _clear_range(ws,start,total_row,1,43 if level=="THCS" else 33)
    display=schools if len(schools)<=max_rows else []
    if not display:
        # Phạm vi lớn: một dòng tổng hợp để không phá bố cục mẫu gốc.
        class_count=sum(_class_count_with_network(db,school_id=int(s.id),school_year_id=school_year_id,grades=grades,level=level) for s in schools)
        merged=[]
        for s in schools: merged.extend(records.get(int(s.id),[]))
        summary=_staff_summary(merged,class_count)
        display_data=[(meta["title"],summary,class_count)]
    else:
        display_data=[]
        for s in display:
            cc=_class_count_with_network(db,school_id=int(s.id),school_year_id=school_year_id,grades=grades,level=level)
            display_data.append((s.name,_staff_summary(records.get(int(s.id),[]),cc),cc))
    for idx,(name,s,cc) in enumerate(display_data,start=1):
        row=start+idx-1
        ws.cell(row,1).value=idx; ws.cell(row,2).value=name
        if level=="TH":
            mapping={7:s["principal"],8:s["vice"],9:s["teachers"],10:s["bienche"],11:s["hopdong"],12:s["female"],13:s["ethnic"],14:s["ratio"],15:s["qual"]["postgrad"],16:s["qual"]["univ"],17:s["qual"]["college"],18:s["qual"]["secondary"],20:s["subjects"]["general"],21:s["subjects"]["music"],22:s["subjects"]["art"],23:s["subjects"]["pe"],24:s["subjects"]["it"],25:s["subjects"]["english"]+s["subjects"]["foreign"],27:s["prof"]["excellent"],28:s["prof"]["good"],29:s["prof"]["average"],30:s["prof"]["poor"],32:s["employees"]["office"],33:s["employees"]["library"]+s["employees"]["equipment"]}
        else:
            mapping={6:s["principal"],7:s["vice"],8:s["teachers"],9:s["bienche"],10:s["hopdong"],11:s["female"],12:s["ethnic"],13:s["ratio"],14:s["qual"]["postgrad"],15:s["qual"]["univ"],16:s["qual"]["college"],17:s["qual"]["secondary"],18:s["subjects"]["math"],19:s["subjects"]["literature"],20:s["subjects"]["physics"],21:s["subjects"]["chemistry"],22:s["subjects"]["biology"],23:s["subjects"]["history"],24:s["subjects"]["geography"],25:s["subjects"]["music"],26:s["subjects"]["art"],27:s["subjects"]["pe"],28:s["subjects"]["civic"],29:s["subjects"]["technology"],30:s["subjects"]["it"],31:s["subjects"]["english"],32:s["subjects"]["russian"],33:s["subjects"]["french"],34:s["subjects"]["other"],36:s["prof"]["excellent"],37:s["prof"]["good"],38:s["prof"]["average"],39:s["prof"]["poor"],40:s["employees"]["library"],41:s["employees"]["equipment"],42:s["employees"]["office"],43:s["employees"]["health"]}
        for c,v in mapping.items(): ws.cell(row,c).value=v or None
    # Dòng cộng
    label_col=1; ws.cell(total_row,label_col).value="Cộng tỉnh:" if meta["kind"]=="province" else "Cộng:"
    for c in range(6 if level=="THCS" else 7,44 if level=="THCS" else 34):
        vals=[ws.cell(r,c).value for r in range(start,start+len(display_data))]
        nums=[v for v in vals if isinstance(v,(int,float))]
        if c==13 and level=="THCS" or c==14 and level=="TH":
            continue
        if nums: ws.cell(total_row,c).value=sum(nums)

    _structured_overlay_export(
        ws=ws,
        db=db,
        school_year_id=school_year_id,
        selected_commune_id=selected_commune_id,
        selected_school_id=selected_school_id,
        level=level,
        form_code="TH_01_GV" if level == "TH" else "THCS_01_GV",
        start_row=start,
        total_row=total_row,
        max_rows=max_rows,
        meta=meta,
        aggregate_if_province=False,
    )


def _write_csvc_detail(ws:Any, report_type:str, db:Session, school_year_id:int, selected_commune_id:int|None, selected_school_id:int|None, level:str, meta:dict[str,str]) -> None:
    schools,grades=_schools_and_classes(db,school_year_id,selected_commune_id,selected_school_id)
    schools=[s for s in schools if _school_supports_report_level(db,s,grades,level)]
    if level=="TH": start,total_row,max_rows=8,18,10
    else: start,total_row,max_rows=8,18,10
    _clear_range(ws,start,total_row,1,35 if level=="TH" else 24)
    if len(schools)>max_rows or meta["kind"]=="province":
        rows=[(meta["title"],sum(_class_count_with_network(db,school_id=int(s.id),school_year_id=school_year_id,grades=grades,level=level) for s in schools))]
    else:
        rows=[(s.name,_class_count_with_network(db,school_id=int(s.id),school_year_id=school_year_id,grades=grades,level=level)) for s in schools]
    for idx,(name,cc) in enumerate(rows,start=1):
        row=start+idx-1; ws.cell(row,1).value=idx; ws.cell(row,2).value=name; ws.cell(row,4).value=cc or None
    ws.cell(total_row,2).value="Cộng tỉnh:" if meta["kind"]=="province" else "Cộng:"
    ws.cell(total_row,4).value=sum(cc for _,cc in rows) or None
    # Các chỉ tiêu chưa có nguồn tự động vẫn được bổ sung từ màn hình nhập chuyên biệt.
    _structured_overlay_export(
        ws=ws,
        db=db,
        school_year_id=school_year_id,
        selected_commune_id=selected_commune_id,
        selected_school_id=selected_school_id,
        level=level,
        form_code="TH_01_CSVC" if level == "TH" else "THCS_01_CSVC",
        start_row=start,
        total_row=total_row,
        max_rows=max_rows,
        meta=meta,
        aggregate_if_province=True,
    )


# === BAI_13B_11_15_2_4_5_TH_THCS_OFFICIAL_CALCULATIONS ===
def _b15245_ws_number(ws: Any, ref: str) -> float | None:
    value = ws[ref].value
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _b15245_ws_sum(ws: Any, refs: tuple[str, ...]) -> float | None:
    values = [_b15245_ws_number(ws, ref) for ref in refs]
    if all(value is None for value in values):
        return None
    return sum(value or 0.0 for value in values)


def _b15245_percent_from_cells(ws: Any, numerator_refs: tuple[str, ...], denominator_refs: tuple[str, ...]) -> float | None:
    from app.services.pcgd_business_rules import safe_percent
    return safe_percent(_b15245_ws_sum(ws, numerator_refs), _b15245_ws_sum(ws, denominator_refs))


def _b15245_ratio_from_cells(ws: Any, numerator_refs: tuple[str, ...], denominator_refs: tuple[str, ...]) -> float | None:
    from app.services.pcgd_business_rules import safe_ratio
    return safe_ratio(_b15245_ws_sum(ws, numerator_refs), _b15245_ws_sum(ws, denominator_refs))


def _b15245_apply_official_th_thcs_calculations(ws: Any, report_type: str) -> None:
    # TIỂU HỌC TH-02: Q8 = P8/O8%
    if report_type == "PCGD_TH_02_2025":
        ws["Q8"] = _b15245_percent_from_cells(ws, ("P8",), ("O8",))
        return

    # TIỂU HỌC CSVC: J = SUM(F:I)/D
    if report_type == "PCGD_TH_01_CSVC_2025":
        for row in range(8, 19):
            refs = tuple(f"{col}{row}" for col in ("F", "G", "H", "I"))
            ws[f"J{row}"] = _b15245_ratio_from_cells(ws, refs, (f"D{row}",))
        return

    # THCS M2: E=D/C%; J=I/F%; M=L/K%; Q=(P+O)/N%; V=U/R%
    if report_type == "PCGD_THCS_M2_2025":
        for row in (14, 15):
            ws[f"E{row}"] = _b15245_percent_from_cells(ws, (f"D{row}",), (f"C{row}",))
            ws[f"J{row}"] = _b15245_percent_from_cells(ws, (f"I{row}",), (f"F{row}",))
            ws[f"M{row}"] = _b15245_percent_from_cells(ws, (f"L{row}",), (f"K{row}",))
            ws[f"Q{row}"] = _b15245_percent_from_cells(ws, (f"P{row}", f"O{row}"), (f"N{row}",))
            ws[f"V{row}"] = _b15245_percent_from_cells(ws, (f"U{row}",), (f"R{row}",))
        _b152451_clean_thcs_m2_evaluation(ws)
        return

    # THCS TK: O8 = N8/M8%
    if report_type == "PCGD_THCS_TK_2025":
        ws["O8"] = _b15245_percent_from_cells(ws, ("N8",), ("M8",))
        return

    # THCS M5: L21:L23 = K/H19%
    if report_type == "PCGD_THCS_M5_2025":
        for row in (21, 22, 23):
            ws[f"L{row}"] = _b15245_percent_from_cells(ws, (f"K{row}",), ("H19",))
        return

    # THCS CSVC: H = SUM(E:G)/D
    if report_type == "PCGD_THCS_CSVC_2025":
        for row in range(8, 19):
            refs = tuple(f"{col}{row}" for col in ("E", "F", "G"))
            ws[f"H{row}"] = _b15245_ratio_from_cells(ws, refs, (f"D{row}",))
        return

# === END BAI_13B_11_15_2_4_5_TH_THCS_OFFICIAL_CALCULATIONS ===


def export_additional_report(
    *,
    report_type: str,
    db: Session,
    request: Any,
    school_year: SchoolYear | None,
    selected_commune_id: int | None,
    selected_school_id: int | None,
    scope_label: str,
) -> StreamingResponse:
    if report_type not in SUPPORTED_REPORT_TYPES:
        raise ValueError(f"Loại báo cáo chưa được hỗ trợ: {report_type}")
    if school_year is None:
        raise ValueError("Chưa xác định được năm học để lập báo cáo.")
    template_path=TEMPLATE_ROOT/REPORT_TEMPLATE_FILES[report_type]
    if not template_path.exists():
        raise FileNotFoundError(f"Không tìm thấy mẫu Excel: {template_path}")
    year=_reference_year(school_year)
    (
        selected_commune_id,
        selected_school_id,
        scope_label,
        _scope_source,
    ) = _effective_scope_for_user(
        db=db,
        request=request,
        selected_commune_id=selected_commune_id,
        selected_school_id=selected_school_id,
        scope_label=scope_label,
    )
    meta=_scope_meta(scope_label=scope_label,selected_commune_id=selected_commune_id,selected_school_id=selected_school_id,year=year)
    people=_load_people_and_records(db=db,request=request,school_year_id=int(school_year.id),selected_commune_id=selected_commune_id,selected_school_id=selected_school_id)
    workbook=load_workbook(template_path)
    ws=workbook[workbook.sheetnames[0]]
    _write_scope_signature(ws,report_type,meta)
    # Thời điểm báo cáo
    date_cells={"PCGD_TH_02_2025":"C2","PCGD_TH_01_GV_2025":"C2","PCGD_TH_01_CSVC_2025":"C2","PCGD_THCS_M1_2025":"F2","PCGD_THCS_M2_2025":"A7","PCGD_THCS_TK_2025":"C2","PCGD_THCS_M5_2025":"G3","PCGD_THCS_CSVC_2025":"C2","PCGD_XMC_4_2025":"A4"}
    if report_type in date_cells: ws[date_cells[report_type]]=f"Thời điểm: ngày 30 tháng 9 năm {year}" if report_type not in {"PCGD_THCS_M2_2025","PCGD_THCS_M5_2025","PCGD_THCS_CSVC_2025"} else (f"Thời điểm điều tra: ngày 30 tháng 9 năm {year}" if report_type=="PCGD_THCS_M2_2025" else f"Tính đến thời điểm: ngày 30 tháng 9 năm {year}")
    schools,grades=_schools_and_classes(db,int(school_year.id),selected_commune_id,selected_school_id)
    primary_count=sum(1 for s in schools if _school_level(s,grades)=="TH")
    thcs_count=sum(1 for s in schools if _school_level(s,grades)=="THCS")
    if report_type=="PCGD_TH_02_2025": _build_th02(ws,people,year,meta,primary_count)
    elif report_type=="PCGD_TH_01_GV_2025": _write_staff_detail(ws,report_type,db,int(school_year.id),selected_commune_id,selected_school_id,"TH",meta)
    elif report_type=="PCGD_TH_01_CSVC_2025": _write_csvc_detail(ws,report_type,db,int(school_year.id),selected_commune_id,selected_school_id,"TH",meta)
    elif report_type=="PCGD_THCS_M1_2025": _build_thcs_m1(ws,people,year,meta,selected_commune_id)
    elif report_type=="PCGD_THCS_M2_2025": _build_thcs_m2(ws,people,year,meta)
    elif report_type=="PCGD_THCS_TK_2025": _build_thcs_tk(ws,people,year,meta,thcs_count)
    elif report_type=="PCGD_THCS_M5_2025": _write_staff_detail(ws,report_type,db,int(school_year.id),selected_commune_id,selected_school_id,"THCS",meta)
    elif report_type=="PCGD_THCS_CSVC_2025": _write_csvc_detail(ws,report_type,db,int(school_year.id),selected_commune_id,selected_school_id,"THCS",meta)
    elif report_type=="PCGD_XMC_3_2025": _build_xmc3(ws,people,year)
    elif report_type=="PCGD_CMC_2_2025": _build_cmc2(ws,people,year)
    elif report_type=="PCGD_CMC_1_2025": _build_cmc1(ws,people,year,meta)
    elif report_type=="PCGD_XMC_4_2025": _build_xmc4(ws,people,year,meta)
    _b15245_apply_official_th_thcs_calculations(ws, report_type)
    if meta["kind"]=="province":
        try: ws.title="Toàn tỉnh"
        except Exception: pass
    # === BAI_13B_11_15_2_4_7_APPLY_XMC_BEFORE_SAVE ===
    if report_type in {
        "PCGD_CMC_1_2025",
        "PCGD_CMC_2_2025",
        "PCGD_XMC_3_2025",
        "PCGD_XMC_4_2025",
    }:
        from app.services.xmc_report_v247 import (
            apply_xmc_formula_contract,
        )
        apply_xmc_formula_contract(
            report_type,
            ws,
        )
    # === BAI_13B_11_15_2_4_9_1_XMC_CALL_START ===
    _b491_apply_xmc_conclusions(
        ws=ws,
        report_type=report_type,
        db=db,
        selected_commune_id=selected_commune_id,
        selected_school_id=selected_school_id,
        meta=meta,
        people=people,
        year=year,
    )
    # === BAI_13B_11_15_2_4_9_1_XMC_CALL_END ===
    # === BAI_13B_11_15_2_4_9_2_XMC_CALL_START ===
    _b492_apply_xmc_province_conclusions(
        ws=ws,
        report_type=report_type,
        db=db,
        request=request,
        school_year=school_year,
        selected_commune_id=selected_commune_id,
        selected_school_id=selected_school_id,
        meta=meta,
        year=year,
    )
    # === BAI_13B_11_15_2_4_9_2_XMC_CALL_END ===
    # === BAI_13B_11_15_2_4_9_2A_1_XMC_CALL_START ===
    _b492a1_format_th_thcs_percent_display(
        ws,
        report_type,
    )
    # === BAI_13B_11_15_2_4_9_2A_1_XMC_CALL_END ===
    # === BAI_13B_12_V2_4_4_1_PCGD_CONDITION_GATE_CALL_START ===
    _b2441_apply_condition_gate(
        ws=ws,
        report_type=report_type,
        db=db,
        school_year_id=int(school_year.id),
        selected_commune_id=selected_commune_id,
        selected_school_id=selected_school_id,
    )
    # === BAI_13B_12_V2_4_4_1_PCGD_CONDITION_GATE_CALL_END ===
    output=BytesIO(); workbook.save(output); output.seek(0)
    year_code=str(school_year.code or year).replace("/","-")
    code=report_type.replace("PCGD_","").replace("_2025","")
    filename=f"PCGD_{code}_{year_code}_{_safe_filename_text(meta['title'])}.xlsx"
    return StreamingResponse(output,media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",headers={"Content-Disposition":f'attachment; filename="{filename}"'})

# === BAI_13B_11_15_2_4_9_1_XMC_HELPERS_START ===
def _b491_special_difficult(db, commune_id: int | None) -> bool:
    if commune_id is None:
        return False

    from sqlalchemy import text as _b491_sql_text

    value = db.execute(
        _b491_sql_text(
            "SELECT is_special_difficulty_area "
            "FROM communes WHERE id=:commune_id"
        ),
        {"commune_id": int(commune_id)},
    ).scalar_one_or_none()

    try:
        return bool(int(value or 0))
    except (TypeError, ValueError):
        return bool(value)


def _b491_result_level_or_status(result):
    if bool(getattr(result, "passed", False)):
        level = getattr(result, "level", None)
        if level is not None:
            return int(level)

    if tuple(getattr(result, "missing_fields", ()) or ()):
        return "Chưa đủ dữ liệu"

    return "Không đạt"


def _b491_primary_metrics(people, year: int):
    age6 = [
        (person, record)
        for person, record in people
        if _age(person, year) == 6 and _is_ppc(person, record)
    ]

    age11 = [
        (person, record)
        for person, record in people
        if _age(person, year) == 11 and _is_ppc(person, record)
    ]

    age14 = [
        (person, record)
        for person, record in people
        if _age(person, year) == 14 and _is_ppc(person, record)
    ]

    grade1_age6 = sum(
        1 for _person, record in age6 if _grade(record) == 1
    )
    completed_age11 = sum(
        1
        for person, record in age11
        if _completed_primary(person, record)
    )
    completed_age14 = sum(
        1
        for person, record in age14
        if _completed_primary(person, record)
    )

    remaining_age11 = [
        (person, record)
        for person, record in age11
        if not _completed_primary(person, record)
    ]

    def _still_primary(record) -> bool:
        grade = _grade(record)
        status = str(
            getattr(record, "learning_status", "") or ""
        ).strip().upper().replace(" ", "_").replace("-", "_")

        return (
            grade in {1, 2, 3, 4, 5}
            and status not in {
                "BO_HOC",
                "THOI_HOC",
                "CHUA_DI_HOC",
                "KHONG_THUOC_DIEN",
            }
        )

    return {
        "age6_grade1_rate": _percent(grade1_age6, len(age6)),
        "age14_completed_rate": _percent(completed_age14, len(age14)),
        "age11_completed_rate": _percent(completed_age11, len(age11)),
        "age11_remaining_all_study_primary": all(
            _still_primary(record)
            for _person, record in remaining_age11
        ),
    }


def _b491_literacy_metrics(people, year: int):
    metrics = _xmc1471b_metrics(people, year)

    def _rate(ages, true_key: str, false_key: str):
        ages = list(ages)
        population = _xmc1471b_sum(metrics, ages, "total")

        if int(population or 0) <= 0:
            return None

        positive = _xmc1471b_sum(metrics, ages, true_key)

        # BAI 13B-12 V2.4.4.2:
        # Dong bo ket luan voi chinh ty le dang hien tren XMC-4.
        # Nguoi chua duoc xac nhan dat muc biet chu khong duoc tinh vao tu so,
        # nhung van nam trong tong dan so cua nhom tuoi (mau so).
        # Vi vay khong bien du lieu chua xac nhan thanh "thieu du lieu" neu
        # bieu da tinh duoc ty le tu tong so va so nguoi duoc cong nhan.
        return _percent(positive, population)

    return {
        "literacy_level1_rate_15_25": _rate(
            range(15, 26),
            "bc1_total",
            "mc1_total",
        ),
        "literacy_level1_rate_15_35": _rate(
            range(15, 36),
            "bc1_total",
            "mc1_total",
        ),
        "literacy_level2_rate_15_35": _rate(
            range(15, 36),
            "bc2_total",
            "mc2_total",
        ),
        "literacy_level2_rate_15_60": _rate(
            range(15, 61),
            "bc2_total",
            "mc2_total",
        ),
    }


def _b491_thcs_metrics(people, year: int):
    age15_18 = [
        (person, record)
        for person, record in people
        if (_age(person, year) or -1) in range(15, 19)
        and _is_ppc(person, record)
    ]

    graduated = sum(
        1
        for person, record in age15_18
        if _completed_secondary(person, record)
    )
    upper = sum(
        1
        for person, record in age15_18
        if _upper_secondary(person, record)
    )

    return {
        "age15_18_graduated_thcs_rate": _percent(
            graduated,
            len(age15_18),
        ),
        "age15_18_upper_program_rate": _percent(
            upper,
            len(age15_18),
        ),
    }


def _b491_evaluate_all(*, db, commune_id: int, people, year: int):
    from app.services.pcgd_business_rules import (
        evaluate_literacy_commune,
        evaluate_primary_commune,
        evaluate_thcs_commune,
    )

    special = _b491_special_difficult(db, commune_id)

    primary = evaluate_primary_commune(
        _b491_primary_metrics(people, year),
        is_special_difficult=special,
    )

    literacy = evaluate_literacy_commune(
        _b491_literacy_metrics(people, year),
        is_special_difficult=special,
    )

    primary_level = (
        int(primary.level)
        if bool(primary.passed) and primary.level is not None
        else None
    )
    literacy_level = (
        int(literacy.level)
        if bool(literacy.passed) and literacy.level is not None
        else None
    )

    primary_missing = tuple(
        getattr(primary, "missing_fields", ()) or ()
    )
    literacy_missing = tuple(
        getattr(literacy, "missing_fields", ()) or ()
    )

    prereq_missing = bool(primary_missing or literacy_missing)
    prereq_failed = bool(
        (not bool(primary.passed) and not primary_missing)
        or (not bool(literacy.passed) and not literacy_missing)
    )

    if prereq_missing:
        thcs = None
        thcs_value = "Chưa đủ dữ liệu"
    elif prereq_failed:
        thcs = None
        thcs_value = "Không đạt"
    else:
        thcs = evaluate_thcs_commune(
            _b491_thcs_metrics(people, year),
            primary_level=primary_level,
            literacy_level=literacy_level,
            is_special_difficult=special,
        )
        thcs_value = _b491_result_level_or_status(thcs)

    return {
        "special": special,
        "primary": primary,
        "primary_value": _b491_result_level_or_status(primary),
        "literacy": literacy,
        "literacy_value": _b491_result_level_or_status(literacy),
        "thcs": thcs,
        "thcs_value": thcs_value,
    }


def _b491_clear_conclusion_cells(ws, report_type: str) -> None:
    mappings = {
        "PCGD_TH_02_2025": ("T8",),
        "PCGD_THCS_M1_2025": ("G36", "G37"),
        "PCGD_THCS_M2_2025": ("W14",),
        "PCGD_THCS_TK_2025": ("F8", "G8", "R8"),
        "PCGD_XMC_4_2025": ("R8",),
    }

    for ref in mappings.get(report_type, ()):
        ws[ref] = None


def _b491_apply_xmc_conclusions(
    *,
    ws,
    report_type: str,
    db,
    selected_commune_id: int | None,
    selected_school_id: int | None,
    meta,
    people,
    year: int,
) -> None:
    supported = {
        "PCGD_TH_02_2025",
        "PCGD_THCS_M1_2025",
        "PCGD_THCS_M2_2025",
        "PCGD_THCS_TK_2025",
        "PCGD_XMC_4_2025",
    }

    if report_type not in supported:
        return

    _b491_clear_conclusion_cells(ws, report_type)

    if (
        selected_commune_id is None
        or selected_school_id is not None
        or str(meta.get("kind") or "") != "commune"
    ):
        return

    result = _b491_evaluate_all(
        db=db,
        commune_id=int(selected_commune_id),
        people=people,
        year=year,
    )

    if report_type == "PCGD_TH_02_2025":
        ws["T8"] = result["primary_value"]

    elif report_type == "PCGD_THCS_M1_2025":
        ws["G36"] = result["primary_value"]
        ws["G37"] = result["literacy_value"]

    elif report_type == "PCGD_THCS_M2_2025":
        ws["W14"] = result["thcs_value"]

    elif report_type == "PCGD_THCS_TK_2025":
        ws["F8"] = result["primary_value"]
        ws["G8"] = result["literacy_value"]
        ws["R8"] = result["thcs_value"]

    elif report_type == "PCGD_XMC_4_2025":
        ws["R8"] = result["literacy_value"]
# === BAI_13B_11_15_2_4_9_1_XMC_HELPERS_END ===

# === BAI_13B_11_15_2_4_9_2_XMC_HELPERS_START ===
def _b492_province_level_item(result):
    if result is None:
        return {"level": None, "incomplete": True}

    missing = bool(tuple(getattr(result, "missing_fields", ()) or ()))
    passed = bool(getattr(result, "passed", False))
    level = getattr(result, "level", None)

    if passed and level is not None:
        try:
            return {"level": int(level), "incomplete": missing}
        except (TypeError, ValueError):
            return {"level": None, "incomplete": True}

    if missing:
        return {"level": None, "incomplete": True}

    return {"level": 0, "incomplete": False}


def _b492_thcs_level_item(result, value):
    if result is not None:
        return _b492_province_level_item(result)

    text = str(value or "").strip()
    if text == "Chưa đủ dữ liệu":
        return {"level": None, "incomplete": True}
    if text == "Không đạt":
        return {"level": 0, "incomplete": False}

    try:
        return {"level": int(value), "incomplete": False}
    except (TypeError, ValueError):
        return {"level": None, "incomplete": True}


def _b492_province_result_value(result):
    if bool(getattr(result, "passed", False)):
        level = getattr(result, "level", None)
        if level is not None:
            return int(level)

    if tuple(getattr(result, "missing_fields", ()) or ()):
        return "Chưa đủ dữ liệu"

    return "Không đạt"


def _b492_evaluate_province_all(
    *,
    db,
    request,
    school_year_id: int,
    year: int,
):
    from sqlalchemy import text as _b492_sql_text
    from app.services.pcgd_business_rules import (
        evaluate_primary_province,
        evaluate_literacy_province,
        evaluate_thcs_province,
    )

    rows = db.execute(
        _b492_sql_text(
            """
            SELECT id
            FROM communes
            WHERE COALESCE(is_active, 1) = 1
            ORDER BY id
            """
        )
    ).all()

    if len(rows) != 130:
        return None

    primary_items = []
    literacy_items = []
    thcs_items = []

    for row in rows:
        commune_id = int(row[0])

        people = _load_people_and_records(
            db=db,
            request=request,
            school_year_id=int(school_year_id),
            selected_commune_id=commune_id,
            selected_school_id=None,
        )

        commune = _b491_evaluate_all(
            db=db,
            commune_id=commune_id,
            people=people,
            year=year,
        )

        primary_items.append(
            _b492_province_level_item(commune["primary"])
        )
        literacy_items.append(
            _b492_province_level_item(commune["literacy"])
        )
        thcs_items.append(
            _b492_thcs_level_item(
                commune["thcs"],
                commune["thcs_value"],
            )
        )

    return {
        "primary": evaluate_primary_province(primary_items),
        "literacy": evaluate_literacy_province(literacy_items),
        "thcs": evaluate_thcs_province(thcs_items),
    }


def _b492_apply_xmc_province_conclusions(
    *,
    ws,
    report_type: str,
    db,
    request,
    school_year,
    selected_commune_id: int | None,
    selected_school_id: int | None,
    meta,
    year: int,
) -> None:
    supported = {
        "PCGD_TH_02_2025",
        "PCGD_THCS_M1_2025",
        "PCGD_THCS_M2_2025",
        "PCGD_THCS_TK_2025",
        "PCGD_XMC_4_2025",
    }

    if report_type not in supported:
        return

    if (
        selected_commune_id is not None
        or selected_school_id is not None
        or str(meta.get("kind") or "") != "province"
    ):
        return

    result = _b492_evaluate_province_all(
        db=db,
        request=request,
        school_year_id=int(school_year.id),
        year=year,
    )

    if result is None:
        primary_value = "Chưa đủ dữ liệu"
        literacy_value = "Chưa đủ dữ liệu"
        thcs_value = "Chưa đủ dữ liệu"
    else:
        primary_value = _b492_province_result_value(result["primary"])
        literacy_value = _b492_province_result_value(result["literacy"])
        thcs_value = _b492_province_result_value(result["thcs"])

    if report_type == "PCGD_TH_02_2025":
        ws["T8"] = primary_value
    elif report_type == "PCGD_THCS_M1_2025":
        ws["G36"] = primary_value
        ws["G37"] = literacy_value
    elif report_type == "PCGD_THCS_M2_2025":
        ws["W14"] = thcs_value
    elif report_type == "PCGD_THCS_TK_2025":
        ws["F8"] = primary_value
        ws["G8"] = literacy_value
        ws["R8"] = thcs_value
    elif report_type == "PCGD_XMC_4_2025":
        ws["R8"] = literacy_value
# === BAI_13B_11_15_2_4_9_2_XMC_HELPERS_END ===

# === BAI_13B_11_15_2_4_9_2A_1_XMC_HELPERS_START ===
def _b492a1_format_th_thcs_percent_display(ws, report_type: str) -> None:
    """
    Chuẩn hóa cách viết tỷ lệ cho TIỂU HỌC và THCS:
        100 -> 100%

    KHÔNG áp dụng cho Xóa mù chữ vì XMC hiện đã đúng.
    KHÔNG thay đổi giá trị/công thức.
    """
    mappings = {
        "PCGD_TH_02_2025": (
            "I8",
            "K8",
            "M8",
            "Q8",
        ),
        "PCGD_THCS_M1_2025": (
            "H39",
            "H40",
            "H41",
        ),
        "PCGD_THCS_M2_2025": (
            "E14",
            "J14",
            "M14",
            "Q14",
            "V14",
            "E15",
            "J15",
            "M15",
            "Q15",
            "V15",
            "K20",
            "K21",
            "K22",
            "K23",
            "K24",
        ),
        "PCGD_THCS_TK_2025": (
            "I8",
            "K8",
            "O8",
        ),
    }

    for ref in mappings.get(report_type, ()):
        ws[ref].number_format = r"0\%"
# === BAI_13B_11_15_2_4_9_2A_1_XMC_HELPERS_END ===


# === BAI_13B_12_V2_4_4_1_PCGD_CONDITION_GATE_HELPERS_START ===
_B2441_STAFF_VERIFY_KEYS = (
    "pcgd_staffing_sufficient",
    "pcgd_teacher_training_standard_all",
    "pcgd_teacher_professional_standard_all",
    "pcgd_tracker_assigned",
)

_B2441_FACILITY_VERIFY_KEYS = (
    "pcgd_classrooms_standard_safe",
    "pcgd_furniture_access_sufficient",
    "pcgd_function_rooms_sufficient",
    "pcgd_minimum_teaching_equipment_sufficient",
    "pcgd_teaching_equipment_regular_use",
    "pcgd_playground_sports_safe",
    "pcgd_clean_water_drainage",
    "pcgd_toilets_separate_hygienic",
)


def _b2441_json_dict(record: Any) -> dict[str, Any]:
    if record is None:
        return {}
    import json as _b2441_json

    try:
        value = _b2441_json.loads(
            getattr(record, "data_json", None) or "{}"
        )
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def _b2441_form_records(
    db: Session,
    *,
    school_year_id: int,
    school_ids: list[int],
    form_code: str,
) -> dict[int, dict[str, Any]]:
    if not school_ids:
        return {}

    from sqlalchemy import select as _b2441_select

    stmt = _b2441_select(
        SchoolStructuredReportInput
    ).where(
        SchoolStructuredReportInput.school_year_id
        == int(school_year_id),
        SchoolStructuredReportInput.school_id.in_(
            [int(x) for x in school_ids]
        ),
        SchoolStructuredReportInput.form_code == form_code,
    )

    result: dict[int, dict[str, Any]] = {}
    for record in db.scalars(stmt).all():
        result[int(record.school_id)] = _b2441_json_dict(record)
    return result


def _b2441_verification_status(
    rows: dict[int, dict[str, Any]],
    school_ids: list[int],
    keys: tuple[str, ...],
) -> tuple[str, list[str]]:
    missing: list[str] = []
    any_no = False

    for school_id in school_ids:
        values = rows.get(int(school_id), {})
        if not values:
            missing.append(
                f"school_id={school_id}: chưa có phiếu xác nhận"
            )
            continue

        for key in keys:
            if key not in values or values.get(key) is None:
                missing.append(
                    f"school_id={school_id}: thiếu {key}"
                )
                continue

            try:
                flag = int(values.get(key))
            except (TypeError, ValueError):
                missing.append(
                    f"school_id={school_id}: {key} không hợp lệ"
                )
                continue

            if flag != 1:
                any_no = True

    if any_no:
        return "Chưa đạt", missing
    if missing:
        return "Chưa xác nhận", missing
    return "Đạt", []


def _b2441_room_ratio_status(
    csvc_rows: dict[int, dict[str, Any]],
    school_ids: list[int],
    *,
    level: str,
) -> tuple[bool | None, list[str]]:
    threshold = 0.7 if level == "TH" else 0.5
    missing: list[str] = []
    passed = True

    for school_id in school_ids:
        values = csvc_rows.get(int(school_id), {})
        try:
            class_total = float(values.get("class_total"))
        except (TypeError, ValueError):
            missing.append(
                f"school_id={school_id}: thiếu class_total"
            )
            continue

        room_keys = [
            "room_permanent",
            "room_semi_permanent",
            "room_temporary",
        ]
        if level == "TH":
            room_keys.append("room_rent_borrow")

        if not any(key in values for key in room_keys):
            missing.append(
                f"school_id={school_id}: thiếu số phòng học"
            )
            continue

        if class_total <= 0:
            missing.append(
                f"school_id={school_id}: class_total <= 0"
            )
            continue

        room_total = 0.0
        invalid = False
        for key in room_keys:
            try:
                room_total += float(values.get(key) or 0)
            except (TypeError, ValueError):
                invalid = True
                missing.append(
                    f"school_id={school_id}: {key} không hợp lệ"
                )

        if invalid:
            continue

        ratio = room_total / class_total
        if ratio + 1e-9 < threshold:
            passed = False

    if missing:
        return None, missing
    return passed, []


def _b2441_condition_state(
    db: Session,
    *,
    school_year_id: int,
    selected_commune_id: int | None,
    selected_school_id: int | None,
    level: str,
) -> dict[str, Any]:
    schools, grades = _schools_and_classes(
        db,
        int(school_year_id),
        selected_commune_id,
        selected_school_id,
    )
    schools = [
        school
        for school in schools
        if _school_supports_report_level(
            db,
            school,
            grades,
            level,
        )
    ]
    school_ids = [int(s.id) for s in schools]

    if not school_ids:
        return {
            "school_ids": [],
            "staff_status": "Chưa xác nhận",
            "csvc_status": "Chưa xác nhận",
            "staff_missing": ["Không có trường trong phạm vi"],
            "csvc_missing": ["Không có trường trong phạm vi"],
            "all_passed": False,
        }

    staff_form = (
        "TH_01_GV"
        if level == "TH"
        else "THCS_01_GV"
    )
    csvc_form = (
        "TH_01_CSVC"
        if level == "TH"
        else "THCS_01_CSVC"
    )

    staff_rows = _b2441_form_records(
        db,
        school_year_id=int(school_year_id),
        school_ids=school_ids,
        form_code=staff_form,
    )
    csvc_rows = _b2441_form_records(
        db,
        school_year_id=int(school_year_id),
        school_ids=school_ids,
        form_code=csvc_form,
    )

    staff_status, staff_missing = _b2441_verification_status(
        staff_rows,
        school_ids,
        _B2441_STAFF_VERIFY_KEYS,
    )
    csvc_status, csvc_missing = _b2441_verification_status(
        csvc_rows,
        school_ids,
        _B2441_FACILITY_VERIFY_KEYS,
    )

    room_passed, room_missing = _b2441_room_ratio_status(
        csvc_rows,
        school_ids,
        level=level,
    )
    csvc_missing.extend(room_missing)

    if room_passed is False:
        csvc_status = "Chưa đạt"
    elif room_passed is None and csvc_status == "Đạt":
        csvc_status = "Chưa xác nhận"

    return {
        "school_ids": school_ids,
        "staff_status": staff_status,
        "csvc_status": csvc_status,
        "staff_missing": staff_missing,
        "csvc_missing": csvc_missing,
        "all_passed": (
            staff_status == "Đạt"
            and csvc_status == "Đạt"
        ),
    }


def _b2441_apply_condition_gate(
    *,
    ws: Any,
    report_type: str,
    db: Session,
    school_year_id: int,
    selected_commune_id: int | None,
    selected_school_id: int | None,
) -> None:
    if report_type == "PCGD_TH_02_2025":
        state = _b2441_condition_state(
            db,
            school_year_id=school_year_id,
            selected_commune_id=selected_commune_id,
            selected_school_id=selected_school_id,
            level="TH",
        )

        ws["R8"] = state["staff_status"]
        ws["S8"] = state["csvc_status"]

        if selected_school_id is not None:
            ws["T8"] = None
        elif not state["all_passed"]:
            # BAI 13B-12 V2.4.4.2:
            # Neu ket qua chi tieu da xac dinh chac chan "Khong dat" thi
            # khong de trang thai dieu kien bao dam ghi de ket luan do.
            # Chi dung "Chua du/Chua dat DK" khi ban than chi tieu chua fail.
            existing_conclusion = str(ws["T8"].value or "").strip().casefold()
            if existing_conclusion == "không đạt".casefold():
                return
            if (
                state["staff_status"] == "Chưa đạt"
                or state["csvc_status"] == "Chưa đạt"
            ):
                ws["T8"] = "Chưa đạt ĐK"
            else:
                ws["T8"] = "Chưa đủ ĐK"
        return

    if report_type in {
        "PCGD_THCS_M2_2025",
        "PCGD_THCS_TK_2025",
    }:
        state = _b2441_condition_state(
            db,
            school_year_id=school_year_id,
            selected_commune_id=selected_commune_id,
            selected_school_id=selected_school_id,
            level="THCS",
        )

        conclusion_ref = (
            "W14"
            if report_type == "PCGD_THCS_M2_2025"
            else "R8"
        )

        if selected_school_id is not None:
            ws[conclusion_ref] = None
        elif not state["all_passed"]:
            # BAI 13B-12 V2.4.4.2:
            # Uu tien mot ket qua "Khong dat" da duoc xac dinh tu cac
            # tieu chi/đieu kien tien quyet; khong ghi de bang "Chua du DK".
            existing_conclusion = str(ws[conclusion_ref].value or "").strip().casefold()
            if existing_conclusion == "không đạt".casefold():
                return
            if (
                state["staff_status"] == "Chưa đạt"
                or state["csvc_status"] == "Chưa đạt"
            ):
                ws[conclusion_ref] = "Chưa đạt ĐK"
            else:
                ws[conclusion_ref] = "Chưa đủ ĐK"
# === BAI_13B_12_V2_4_4_1_PCGD_CONDITION_GATE_HELPERS_END ===
# BAI_13B_12_V2_4_4_1_PCGD_CONDITION_GATE

# BAI_13B_12_V2_4_4_2_CONCLUSION_PRIORITY

# === BAI_13B_12_V2_4_4_3_TH02_AUTO_CONDITIONS_START ===
# Hoàn thiện TH-02 cấp xã:
# - Cột 18, 19 tự xác nhận từ dữ liệu đã có, không ghi DB.
# - Giữ ưu tiên cờ xác nhận tường minh nếu người dùng đã lưu trước đó.
# - Không thay logic THCS của V2.4.4.2.
# - Cột 20 chỉ giữ mức độ PCGD khi cả đội ngũ và CSVC/TBDH đều bảo đảm.

_B2443_STAFF_PASS = {"DAT CHUAN", "TREN CHUAN", "DAT", "KHA", "TOT"}
_B2443_STAFF_FAIL = {"CHUA DAT", "DUOI CHUAN", "KHONG DAT"}


def _b2443_flag(values: dict[str, Any], key: str) -> bool | None:
    if key not in values or values.get(key) is None:
        return None
    value = values.get(key)
    if value is True:
        return True
    if value is False:
        return False
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = None
    if number == 1:
        return True
    if number == 0:
        return False
    text = _norm(value)
    if text in {"CO", "YES", "TRUE", "DAT", "DAM BAO"}:
        return True
    if text in {"KHONG", "NO", "FALSE", "CHUA DAT", "KHONG DAT", "KHONG DAM BAO"}:
        return False
    return None


def _b2443_number(values: dict[str, Any], key: str) -> float | None:
    value = values.get(key)
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _b2443_status(flags: list[bool | None]) -> str:
    if any(flag is False for flag in flags):
        return "Chưa đạt"
    if any(flag is None for flag in flags):
        return "Chưa xác nhận"
    return "Đạt"


def _b2443_display_status(status: str) -> str:
    return {
        "Đạt": "Đảm bảo",
        "Chưa đạt": "Không đảm bảo",
        "Chưa xác nhận": "Chưa đủ dữ liệu",
    }.get(str(status or ""), str(status or ""))


def _b2443_staff_row_is_th(row: StaffYearRecord) -> bool:
    source_level = str(getattr(row, "source_level", "") or "").strip().upper()
    teaching_level = str(getattr(row, "teaching_level", "") or "").strip().upper()
    if source_level == "TH":
        return True
    if source_level == "THCS":
        return False
    if teaching_level in {"TIEU_HOC", "LIEN_CAP_TH_THCS"}:
        return True
    if teaching_level == "THCS":
        return False
    return True


def _b2443_staff_reference_rows(
    db: Session,
    *,
    school_id: int,
    school_year_id: int,
) -> list[StaffYearRecord]:
    exact = [
        row
        for row in _staff_rows(db, int(school_year_id), [int(school_id)]).get(int(school_id), [])
        if _b2443_staff_row_is_th(row)
        and _norm(getattr(row, "status_code", "")) in {"DANG LAM VIEC", ""}
    ]
    if exact:
        return exact

    rows = list(
        db.scalars(
            select(StaffYearRecord)
            .where(
                StaffYearRecord.school_id == int(school_id),
                StaffYearRecord.is_active.is_(True),
            )
            .options(selectinload(StaffYearRecord.staff_member))
        ).all()
    )
    rows = [
        row for row in rows
        if _b2443_staff_row_is_th(row)
        and _norm(getattr(row, "status_code", "")) in {"DANG LAM VIEC", ""}
    ]
    if not rows:
        return []

    target_year = db.get(SchoolYear, int(school_year_id))
    target_start = _network_year_start(getattr(target_year, "code", None))
    by_year: dict[int, list[StaffYearRecord]] = defaultdict(list)
    for row in rows:
        by_year[int(row.school_year_id)].append(row)

    candidates: list[tuple[int, int, int]] = []
    for year_id in by_year:
        year_obj = db.get(SchoolYear, int(year_id))
        start = _network_year_start(getattr(year_obj, "code", None))
        candidates.append((1 if (not target_start or start <= target_start) else 0, start, int(year_id)))
    _valid, _start, chosen_year_id = max(candidates)
    return list(by_year.get(int(chosen_year_id), []))


def _b2443_school_has_pcgd_responsible_account(db: Session, school_id: int) -> bool:
    # Trong dữ liệu hiện có chưa có bảng riêng "người theo dõi PCGD-XMC".
    # Tài khoản trường đang hoạt động được dùng làm đầu mối vận hành hệ thống;
    # cờ xác nhận tường minh pcgd_tracker_assigned (nếu đã lưu) vẫn được ưu tiên.
    try:
        from app.models import User, Role
        stmt = (
            select(User.id)
            .join(Role, User.role_id == Role.id)
            .where(
                User.school_id == int(school_id),
                User.is_active.is_(True),
                Role.code == SCHOOL_ROLE_CODE,
            )
            .limit(1)
        )
        return db.scalar(stmt) is not None
    except Exception:
        return False


def _b2443_qualification_from_saved(values: dict[str, Any]) -> bool | None:
    teacher_total = _b2443_number(values, "teacher_total")
    if teacher_total is None:
        return None
    keys = ("qual_postgrad", "qual_university", "qual_college", "qual_secondary", "qual_below_secondary")
    if not all(key in values and values.get(key) is not None for key in keys):
        return None
    qualified = sum(_b2443_number(values, key) or 0 for key in keys[:-1])
    below = _b2443_number(values, "qual_below_secondary") or 0
    if abs((qualified + below) - teacher_total) > 0.001:
        return None
    return below <= 0.001


def _b2443_professional_from_saved(values: dict[str, Any]) -> bool | None:
    teacher_total = _b2443_number(values, "teacher_total")
    if teacher_total is None:
        return None
    keys = ("prof_excellent", "prof_good", "prof_average", "prof_poor")
    if not all(key in values and values.get(key) is not None for key in keys):
        return None
    total = sum(_b2443_number(values, key) or 0 for key in keys)
    if abs(total - teacher_total) > 0.001:
        return None
    return (_b2443_number(values, "prof_poor") or 0) <= 0.001


def _b2443_staff_status_for_school(
    db: Session,
    *,
    school_id: int,
    school_year_id: int,
    grades: dict[int, list[int]],
    saved_staff: dict[str, Any],
    saved_csvc: dict[str, Any],
) -> tuple[str, list[str]]:
    missing: list[str] = []
    records = _b2443_staff_reference_rows(
        db,
        school_id=int(school_id),
        school_year_id=int(school_year_id),
    )
    teachers = [row for row in records if _norm(getattr(row, "position_group", "")) == "GIAO VIEN"]
    class_total = _class_count_with_network(
        db,
        school_id=int(school_id),
        school_year_id=int(school_year_id),
        grades=grades,
        level="TH",
    )

    staffing = _b2443_flag(saved_staff, "pcgd_staffing_sufficient")
    if staffing is None:
        teacher_total: float | None = float(len(teachers)) if teachers else _b2443_number(saved_staff, "teacher_total")
        if teacher_total is None:
            network = _network_reference_data(
                db,
                school_id=int(school_id),
                level="TH",
                target_year_id=int(school_year_id),
            )
            try:
                teacher_total = float(network.get("teachers")) if network.get("teachers") is not None else None
            except (TypeError, ValueError):
                teacher_total = None
        if class_total <= 0 or teacher_total is None:
            staffing = None
            missing.append(f"school_id={school_id}: chưa đủ dữ liệu giáo viên/lớp")
        else:
            # Dữ liệu hiện có không lưu định mức biên chế chi tiết theo từng loại trường.
            # Điều kiện tự động tối thiểu: mỗi lớp có ít nhất một giáo viên; cờ xác nhận
            # tường minh (nếu có) luôn được ưu tiên hơn phép suy ra này.
            staffing = teacher_total + 1e-9 >= float(class_total)

    qualification = _b2443_flag(saved_staff, "pcgd_teacher_training_standard_all")
    if qualification is None:
        if teachers:
            flags: list[bool | None] = []
            for row in teachers:
                text = _norm(getattr(row, "qualification_standard", ""))
                if text in _B2443_STAFF_PASS:
                    flags.append(True)
                elif text in _B2443_STAFF_FAIL:
                    flags.append(False)
                else:
                    flags.append(None)
            if flags and all(flag is not None for flag in flags):
                qualification = all(bool(flag) for flag in flags)
        if qualification is None:
            qualification = _b2443_qualification_from_saved(saved_staff)
        if qualification is None:
            missing.append(f"school_id={school_id}: chưa xác định đủ chuẩn trình độ giáo viên")

    professional = _b2443_flag(saved_staff, "pcgd_teacher_professional_standard_all")
    if professional is None:
        if teachers:
            flags = []
            for row in teachers:
                text = _norm(getattr(row, "professional_standard", ""))
                if text in {"DAT", "KHA", "TOT"}:
                    flags.append(True)
                elif text in {"CHUA DAT", "KHONG DAT"}:
                    flags.append(False)
                else:
                    flags.append(None)
            if flags and all(flag is not None for flag in flags):
                professional = all(bool(flag) for flag in flags)
        if professional is None:
            professional = _b2443_professional_from_saved(saved_staff)
        if professional is None:
            missing.append(f"school_id={school_id}: chưa xác định đủ chuẩn nghề nghiệp giáo viên")

    tracker = _b2443_flag(saved_staff, "pcgd_tracker_assigned")
    if tracker is None:
        pcgd_text = any(
            any(token in _norm(" ".join([
                str(getattr(row, "position_title", "") or ""),
                str(getattr(row, "notes", "") or ""),
            ])) for token in ("PCGD", "PHO CAP", "XMC", "XOA MU"))
            for row in records
        )
        tracker = bool(pcgd_text or saved_staff or saved_csvc or _b2443_school_has_pcgd_responsible_account(db, int(school_id)))
        if not tracker:
            missing.append(f"school_id={school_id}: chưa xác định đầu mối theo dõi PCGD-XMC")
            tracker = None

    status = _b2443_status([staffing, qualification, professional, tracker])
    return status, missing


_B2443_CSVC_CORE_FIELDS = (
    "principal_office_count",
    "vice_office_count",
    "office_room_count",
    "health_room_count",
    "team_activity_room_count",
    "meeting_room_count",
    "library_room_count",
    "equipment_room_count",
    "teacher_toilet_count",
    "student_toilet_count",
    "playground_count",
    "sports_ground_count",
)


def _b2443_csvc_effective_values(
    db: Session,
    *,
    school_id: int,
    school_year_id: int,
    grades: dict[int, list[int]],
    saved: dict[str, Any],
) -> dict[str, Any]:
    values = dict(saved or {})
    if values.get("class_total") is None:
        cc = _class_count_with_network(
            db,
            school_id=int(school_id),
            school_year_id=int(school_year_id),
            grades=grades,
            level="TH",
        )
        if cc:
            values["class_total"] = cc
    network = _network_reference_data(
        db,
        school_id=int(school_id),
        level="TH",
        target_year_id=int(school_year_id),
    )
    for source, target in (
        ("rooms_permanent", "room_permanent"),
        ("rooms_semi_permanent", "room_semi_permanent"),
        ("rooms_temporary", "room_temporary"),
        ("rooms_rent_borrow", "room_rent_borrow"),
    ):
        if values.get(target) is None and network.get(source) is not None:
            values[target] = network.get(source)
    return values


def _b2443_csvc_status_for_school(
    db: Session,
    *,
    school_id: int,
    school_year_id: int,
    grades: dict[int, list[int]],
    saved: dict[str, Any],
) -> tuple[str, list[str]]:
    missing: list[str] = []
    values = _b2443_csvc_effective_values(
        db,
        school_id=int(school_id),
        school_year_id=int(school_year_id),
        grades=grades,
        saved=saved,
    )

    classes = _b2443_number(values, "class_total")
    room_values = [_b2443_number(values, key) for key in ("room_permanent", "room_semi_permanent", "room_temporary", "room_rent_borrow")]
    if classes is None or classes <= 0 or all(value is None for value in room_values):
        room_ok = None
        missing.append(f"school_id={school_id}: chưa đủ số lớp/phòng học")
    else:
        room_total = sum(value or 0 for value in room_values)
        room_ok = (room_total / classes) + 1e-9 >= 0.7

    # Các nhóm số liệu cốt lõi của TH-01-CSVC đã được nhập đủ thì được xem là
    # phiếu CSVC đã hoàn tất. Đây là nguồn kế thừa để không buộc người dùng
    # nhập lại các checkbox định tính mới bổ sung ở V2.4.4.1.
    detail_complete = bool(saved) and all(
        key in saved and saved.get(key) is not None
        for key in _B2443_CSVC_CORE_FIELDS
    )

    function_values = [_b2443_number(values, key) for key in (
        "principal_office_count", "vice_office_count", "office_room_count",
        "health_room_count", "team_activity_room_count", "meeting_room_count",
        "library_room_count", "equipment_room_count",
    )]
    function_ok: bool | None
    if any(value is None for value in function_values):
        function_ok = None
        missing.append(f"school_id={school_id}: chưa đủ dữ liệu phòng chức năng")
    else:
        function_ok = all((value or 0) > 0 for value in function_values)

    equipment_count = _b2443_number(values, "equipment_room_count")
    playground = _b2443_number(values, "playground_count")
    sports = _b2443_number(values, "sports_ground_count")
    teacher_toilet = _b2443_number(values, "teacher_toilet_count")
    student_toilet = _b2443_number(values, "student_toilet_count")

    classroom_safe = _b2443_flag(values, "pcgd_classrooms_standard_safe")
    if classroom_safe is None:
        classroom_safe = True if detail_complete and room_ok is True else (False if room_ok is False else None)

    furniture = _b2443_flag(values, "pcgd_furniture_access_sufficient")
    if furniture is None:
        furniture = True if detail_complete and room_ok is True else None

    function_flag = _b2443_flag(values, "pcgd_function_rooms_sufficient")
    if function_flag is None:
        function_flag = function_ok

    minimum_equipment = _b2443_flag(values, "pcgd_minimum_teaching_equipment_sufficient")
    if minimum_equipment is None:
        minimum_equipment = (equipment_count > 0) if equipment_count is not None and detail_complete else None

    equipment_use = _b2443_flag(values, "pcgd_teaching_equipment_regular_use")
    if equipment_use is None:
        equipment_use = True if detail_complete and equipment_count is not None and equipment_count > 0 else None

    playground_safe = _b2443_flag(values, "pcgd_playground_sports_safe")
    if playground_safe is None:
        if playground is None or sports is None:
            playground_safe = None
        else:
            playground_safe = playground > 0 and sports > 0

    clean_water = _b2443_flag(values, "pcgd_clean_water_drainage")
    if clean_water is None:
        # TH-01-CSVC hiện chưa có cột số riêng cho nước sạch/thoát nước.
        # Khi phiếu cốt lõi đã nhập đủ và không có cờ phủ định, kế thừa việc
        # hoàn tất phiếu như xác nhận vận hành; nếu có cờ tường minh thì cờ đó ưu tiên.
        clean_water = True if detail_complete else None

    toilets = _b2443_flag(values, "pcgd_toilets_separate_hygienic")
    if toilets is None:
        if teacher_toilet is None or student_toilet is None:
            toilets = None
        else:
            toilets = teacher_toilet > 0 and student_toilet > 0

    flags = [
        room_ok,
        classroom_safe,
        furniture,
        function_flag,
        minimum_equipment,
        equipment_use,
        playground_safe,
        clean_water,
        toilets,
    ]
    if any(flag is None for flag in flags):
        missing.append(f"school_id={school_id}: phiếu TH-01-CSVC chưa đủ để tự xác nhận toàn bộ điều kiện")
    return _b2443_status(flags), missing


# Giữ nguyên logic THCS V2.4.4.2 để tránh tác động ngoài phạm vi bài này.
_b2443_legacy_condition_state = _b2441_condition_state
_b2443_legacy_apply_condition_gate = _b2441_apply_condition_gate


def _b2441_condition_state(
    db: Session,
    *,
    school_year_id: int,
    selected_commune_id: int | None,
    selected_school_id: int | None,
    level: str,
) -> dict[str, Any]:
    if level != "TH":
        return _b2443_legacy_condition_state(
            db,
            school_year_id=school_year_id,
            selected_commune_id=selected_commune_id,
            selected_school_id=selected_school_id,
            level=level,
        )

    schools, grades = _schools_and_classes(
        db,
        int(school_year_id),
        selected_commune_id,
        selected_school_id,
    )
    schools = [
        school for school in schools
        if _school_supports_report_level(db, school, grades, "TH")
    ]
    school_ids = [int(s.id) for s in schools]
    if not school_ids:
        return {
            "school_ids": [],
            "staff_status": "Chưa xác nhận",
            "csvc_status": "Chưa xác nhận",
            "staff_missing": ["Không có trường Tiểu học trong phạm vi"],
            "csvc_missing": ["Không có trường Tiểu học trong phạm vi"],
            "all_passed": False,
        }

    staff_rows = _b2441_form_records(
        db,
        school_year_id=int(school_year_id),
        school_ids=school_ids,
        form_code="TH_01_GV",
    )
    csvc_rows = _b2441_form_records(
        db,
        school_year_id=int(school_year_id),
        school_ids=school_ids,
        form_code="TH_01_CSVC",
    )

    staff_statuses: list[str] = []
    csvc_statuses: list[str] = []
    staff_missing: list[str] = []
    csvc_missing: list[str] = []

    for school_id in school_ids:
        staff_status, staff_notes = _b2443_staff_status_for_school(
            db,
            school_id=int(school_id),
            school_year_id=int(school_year_id),
            grades=grades,
            saved_staff=staff_rows.get(int(school_id), {}),
            saved_csvc=csvc_rows.get(int(school_id), {}),
        )
        csvc_status, csvc_notes = _b2443_csvc_status_for_school(
            db,
            school_id=int(school_id),
            school_year_id=int(school_year_id),
            grades=grades,
            saved=csvc_rows.get(int(school_id), {}),
        )
        staff_statuses.append(staff_status)
        csvc_statuses.append(csvc_status)
        staff_missing.extend(staff_notes)
        csvc_missing.extend(csvc_notes)

    def aggregate(statuses: list[str]) -> str:
        if "Chưa đạt" in statuses:
            return "Chưa đạt"
        if "Chưa xác nhận" in statuses:
            return "Chưa xác nhận"
        return "Đạt"

    staff_status = aggregate(staff_statuses)
    csvc_status = aggregate(csvc_statuses)
    return {
        "school_ids": school_ids,
        "staff_status": staff_status,
        "csvc_status": csvc_status,
        "staff_missing": staff_missing,
        "csvc_missing": csvc_missing,
        "all_passed": staff_status == "Đạt" and csvc_status == "Đạt",
    }


def _b2441_apply_condition_gate(
    *,
    ws: Any,
    report_type: str,
    db: Session,
    school_year_id: int,
    selected_commune_id: int | None,
    selected_school_id: int | None,
) -> None:
    if report_type != "PCGD_TH_02_2025":
        return _b2443_legacy_apply_condition_gate(
            ws=ws,
            report_type=report_type,
            db=db,
            school_year_id=school_year_id,
            selected_commune_id=selected_commune_id,
            selected_school_id=selected_school_id,
        )

    state = _b2441_condition_state(
        db,
        school_year_id=school_year_id,
        selected_commune_id=selected_commune_id,
        selected_school_id=selected_school_id,
        level="TH",
    )

    ws["R8"] = _b2443_display_status(state["staff_status"])
    ws["S8"] = _b2443_display_status(state["csvc_status"])

    if selected_school_id is not None:
        ws["T8"] = None
        return

    existing = ws["T8"].value
    existing_text = str(existing or "").strip().casefold()

    # Chỉ tiêu trẻ đã không đạt thì giữ "Không đạt" bất kể trạng thái điều kiện.
    if existing_text == "không đạt".casefold():
        return

    if state["staff_status"] == "Chưa đạt" or state["csvc_status"] == "Chưa đạt":
        ws["T8"] = "Không đạt"
        return

    if not state["all_passed"]:
        ws["T8"] = "Chưa đủ dữ liệu"
        return

    # Khi cả cột 18 và 19 đều Đảm bảo, giữ nguyên mức độ 1/2/3 hoặc trạng thái
    # đã được bộ quy tắc PCGD Tiểu học xác định trước đó.
    if existing in (None, ""):
        ws["T8"] = "Chưa đủ dữ liệu"


# BAI_13B_12_V2_4_4_3_TH02_AUTO_CONDITIONS
# === BAI_13B_12_V2_4_4_3_TH02_AUTO_CONDITIONS_END ===

# === BAI_13B_12_V2_4_4_4_TH02_REUSE_PRIOR_DATA_START ===
# Hoàn thiện nguồn dữ liệu TH-02 mà không yêu cầu nhập lại:
# - TH-01-GV/TH-01-CSVC: ưu tiên năm hiện tại; nếu thiếu trường/chỉ tiêu thì
#   kế thừa đúng bản gần nhất của năm trước, năm hiện tại luôn ghi đè năm cũ.
# - Hồ sơ giáo viên: nếu năm hiện tại đã rollover nhưng chuẩn trình độ/chuẩn
#   nghề nghiệp còn CHƯA_XÁC_ĐỊNH, tra lại hồ sơ gần nhất của chính giáo viên đó.
# - Số lớp/phòng hiện tại (nếu có) luôn ưu tiên dữ liệu mạng lưới hiện hành,
#   không để số của phiếu năm trước ghi đè.
# - Chỉ đọc dữ liệu; tuyệt đối không ghi database.

_b2444_previous_condition_state = _b2441_condition_state
_b2444_previous_staff_status_for_school = _b2443_staff_status_for_school


def _b2444_year_start(db: Session, school_year_id: int) -> int:
    year = db.get(SchoolYear, int(school_year_id))
    return _network_year_start(getattr(year, "code", None))


def _b2444_json_values(record: Any) -> dict[str, Any]:
    if record is None:
        return {}
    return _b2441_json_dict(record)


def _b2444_form_records_with_prior(
    db: Session,
    *,
    school_year_id: int,
    school_ids: list[int],
    form_code: str,
) -> dict[int, dict[str, Any]]:
    """Current form + nearest previous form as read-only fallback.

    Only the nearest previous school year is used.  Current values, including 0
    and False, override previous values.  Blank/None current values do not erase
    a valid previous value because that is exactly the rollover case this patch
    is intended to handle.
    """
    if not school_ids:
        return {}

    rows = list(
        db.scalars(
            select(SchoolStructuredReportInput).where(
                SchoolStructuredReportInput.school_id.in_([int(x) for x in school_ids]),
                SchoolStructuredReportInput.form_code == str(form_code),
            )
        ).all()
    )

    target_start = _b2444_year_start(db, int(school_year_id))
    grouped: dict[int, list[Any]] = defaultdict(list)
    for record in rows:
        grouped[int(record.school_id)].append(record)

    result: dict[int, dict[str, Any]] = {}
    for school_id in [int(x) for x in school_ids]:
        records = grouped.get(int(school_id), [])
        current = next(
            (record for record in records if int(record.school_year_id) == int(school_year_id)),
            None,
        )

        previous_candidates: list[tuple[int, int, Any]] = []
        for record in records:
            if int(record.school_year_id) == int(school_year_id):
                continue
            start = _b2444_year_start(db, int(record.school_year_id))
            if target_start and (not start or start > target_start):
                continue
            previous_candidates.append((start, int(record.school_year_id), record))

        previous = max(previous_candidates, default=(0, 0, None))[2]
        merged = dict(_b2444_json_values(previous))
        for key, value in _b2444_json_values(current).items():
            if value is not None and value != "":
                merged[key] = value

        if merged:
            result[int(school_id)] = merged

    return result


def _b2444_prior_staff_by_member(
    db: Session,
    *,
    school_id: int,
    school_year_id: int,
) -> dict[int, StaffYearRecord]:
    target_start = _b2444_year_start(db, int(school_year_id))
    rows = list(
        db.scalars(
            select(StaffYearRecord)
            .where(
                StaffYearRecord.school_id == int(school_id),
                StaffYearRecord.is_active.is_(True),
                StaffYearRecord.school_year_id != int(school_year_id),
            )
            .options(
                selectinload(StaffYearRecord.staff_member),
                selectinload(StaffYearRecord.school_year),
            )
        ).all()
    )
    chosen: dict[int, tuple[int, StaffYearRecord]] = {}
    for row in rows:
        if not _b2443_staff_row_is_th(row):
            continue
        if _norm(getattr(row, "status_code", "")) not in {"DANG LAM VIEC", ""}:
            continue
        start = _network_year_start(getattr(getattr(row, "school_year", None), "code", None))
        if target_start and (not start or start > target_start):
            continue
        member_id = int(row.staff_member_id)
        old = chosen.get(member_id)
        if old is None or start > old[0]:
            chosen[member_id] = (start, row)
    return {member_id: pair[1] for member_id, pair in chosen.items()}


def _b2444_teacher_flag_from_records(
    teachers: list[StaffYearRecord],
    previous_by_member: dict[int, StaffYearRecord],
    *,
    attr: str,
    pass_values: set[str],
    fail_values: set[str],
) -> bool | None:
    if not teachers:
        return None
    flags: list[bool | None] = []
    for row in teachers:
        text = _norm(getattr(row, attr, ""))
        if text in pass_values:
            flags.append(True)
            continue
        if text in fail_values:
            flags.append(False)
            continue
        old = previous_by_member.get(int(row.staff_member_id))
        old_text = _norm(getattr(old, attr, "")) if old is not None else ""
        if old_text in pass_values:
            flags.append(True)
        elif old_text in fail_values:
            flags.append(False)
        else:
            flags.append(None)
    if any(flag is False for flag in flags):
        return False
    if any(flag is None for flag in flags):
        return None
    return True


def _b2443_staff_status_for_school(
    db: Session,
    *,
    school_id: int,
    school_year_id: int,
    grades: dict[int, list[int]],
    saved_staff: dict[str, Any],
    saved_csvc: dict[str, Any],
) -> tuple[str, list[str]]:
    # Bắt đầu từ cùng bộ điều kiện V2.4.4.3, nhưng bổ sung fallback theo chính
    # giáo viên ở năm gần nhất trước khi kết luận là thiếu dữ liệu.
    missing: list[str] = []
    records = _b2443_staff_reference_rows(
        db,
        school_id=int(school_id),
        school_year_id=int(school_year_id),
    )
    teachers = [row for row in records if _norm(getattr(row, "position_group", "")) == "GIAO VIEN"]
    previous_by_member = _b2444_prior_staff_by_member(
        db,
        school_id=int(school_id),
        school_year_id=int(school_year_id),
    )
    class_total = _class_count_with_network(
        db,
        school_id=int(school_id),
        school_year_id=int(school_year_id),
        grades=grades,
        level="TH",
    )

    staffing = _b2443_flag(saved_staff, "pcgd_staffing_sufficient")
    if staffing is None:
        teacher_total: float | None = float(len(teachers)) if teachers else _b2443_number(saved_staff, "teacher_total")
        if teacher_total is None:
            network = _network_reference_data(
                db,
                school_id=int(school_id),
                level="TH",
                target_year_id=int(school_year_id),
            )
            try:
                teacher_total = float(network.get("teachers")) if network.get("teachers") is not None else None
            except (TypeError, ValueError):
                teacher_total = None
        if class_total <= 0 or teacher_total is None:
            staffing = None
            missing.append(f"school_id={school_id}: chưa đủ dữ liệu giáo viên/lớp")
        else:
            staffing = teacher_total + 1e-9 >= float(class_total)

    qualification = _b2443_flag(saved_staff, "pcgd_teacher_training_standard_all")
    if qualification is None:
        qualification = _b2444_teacher_flag_from_records(
            teachers,
            previous_by_member,
            attr="qualification_standard",
            pass_values=_B2443_STAFF_PASS,
            fail_values=_B2443_STAFF_FAIL,
        )
    if qualification is None:
        qualification = _b2443_qualification_from_saved(saved_staff)
    if qualification is None:
        missing.append(f"school_id={school_id}: chưa xác định đủ chuẩn trình độ giáo viên")

    professional = _b2443_flag(saved_staff, "pcgd_teacher_professional_standard_all")
    if professional is None:
        professional = _b2444_teacher_flag_from_records(
            teachers,
            previous_by_member,
            attr="professional_standard",
            pass_values={"DAT", "KHA", "TOT"},
            fail_values={"CHUA DAT", "KHONG DAT"},
        )
    if professional is None:
        professional = _b2443_professional_from_saved(saved_staff)
    if professional is None:
        missing.append(f"school_id={school_id}: chưa xác định đủ chuẩn nghề nghiệp giáo viên")

    tracker = _b2443_flag(saved_staff, "pcgd_tracker_assigned")
    if tracker is None:
        pcgd_text = any(
            any(token in _norm(" ".join([
                str(getattr(row, "position_title", "") or ""),
                str(getattr(row, "notes", "") or ""),
            ])) for token in ("PCGD", "PHO CAP", "XMC", "XOA MU"))
            for row in records
        )
        tracker = bool(pcgd_text or saved_staff or saved_csvc or _b2443_school_has_pcgd_responsible_account(db, int(school_id)))
        if not tracker:
            missing.append(f"school_id={school_id}: chưa xác định đầu mối theo dõi PCGD-XMC")
            tracker = None

    return _b2443_status([staffing, qualification, professional, tracker]), missing


def _b2444_currentize_csvc_values(
    db: Session,
    *,
    school_id: int,
    school_year_id: int,
    grades: dict[int, list[int]],
    saved: dict[str, Any],
) -> dict[str, Any]:
    values = dict(saved or {})
    current_classes = _class_count_with_network(
        db,
        school_id=int(school_id),
        school_year_id=int(school_year_id),
        grades=grades,
        level="TH",
    )
    if current_classes > 0:
        values["class_total"] = current_classes

    network = _network_reference_data(
        db,
        school_id=int(school_id),
        level="TH",
        target_year_id=int(school_year_id),
    )
    for source, target in (
        ("rooms_permanent", "room_permanent"),
        ("rooms_semi_permanent", "room_semi_permanent"),
        ("rooms_temporary", "room_temporary"),
        ("rooms_rent_borrow", "room_rent_borrow"),
    ):
        if network.get(source) is not None:
            values[target] = network.get(source)
    return values


def _b2441_condition_state(
    db: Session,
    *,
    school_year_id: int,
    selected_commune_id: int | None,
    selected_school_id: int | None,
    level: str,
) -> dict[str, Any]:
    if level != "TH":
        return _b2444_previous_condition_state(
            db,
            school_year_id=school_year_id,
            selected_commune_id=selected_commune_id,
            selected_school_id=selected_school_id,
            level=level,
        )

    schools, grades = _schools_and_classes(
        db,
        int(school_year_id),
        selected_commune_id,
        selected_school_id,
    )
    schools = [
        school for school in schools
        if _school_supports_report_level(db, school, grades, "TH")
    ]
    school_ids = [int(s.id) for s in schools]
    if not school_ids:
        return {
            "school_ids": [],
            "staff_status": "Chưa xác nhận",
            "csvc_status": "Chưa xác nhận",
            "staff_missing": ["Không có trường Tiểu học trong phạm vi"],
            "csvc_missing": ["Không có trường Tiểu học trong phạm vi"],
            "all_passed": False,
        }

    staff_rows = _b2444_form_records_with_prior(
        db,
        school_year_id=int(school_year_id),
        school_ids=school_ids,
        form_code="TH_01_GV",
    )
    csvc_rows = _b2444_form_records_with_prior(
        db,
        school_year_id=int(school_year_id),
        school_ids=school_ids,
        form_code="TH_01_CSVC",
    )

    staff_statuses: list[str] = []
    csvc_statuses: list[str] = []
    staff_missing: list[str] = []
    csvc_missing: list[str] = []

    for school_id in school_ids:
        saved_staff = staff_rows.get(int(school_id), {})
        saved_csvc = _b2444_currentize_csvc_values(
            db,
            school_id=int(school_id),
            school_year_id=int(school_year_id),
            grades=grades,
            saved=csvc_rows.get(int(school_id), {}),
        )
        staff_status, staff_notes = _b2443_staff_status_for_school(
            db,
            school_id=int(school_id),
            school_year_id=int(school_year_id),
            grades=grades,
            saved_staff=saved_staff,
            saved_csvc=saved_csvc,
        )
        csvc_status, csvc_notes = _b2443_csvc_status_for_school(
            db,
            school_id=int(school_id),
            school_year_id=int(school_year_id),
            grades=grades,
            saved=saved_csvc,
        )
        staff_statuses.append(staff_status)
        csvc_statuses.append(csvc_status)
        staff_missing.extend(staff_notes)
        csvc_missing.extend(csvc_notes)

    def aggregate(statuses: list[str]) -> str:
        if "Chưa đạt" in statuses:
            return "Chưa đạt"
        if "Chưa xác nhận" in statuses:
            return "Chưa xác nhận"
        return "Đạt"

    staff_status = aggregate(staff_statuses)
    csvc_status = aggregate(csvc_statuses)
    return {
        "school_ids": school_ids,
        "staff_status": staff_status,
        "csvc_status": csvc_status,
        "staff_missing": staff_missing,
        "csvc_missing": csvc_missing,
        "all_passed": staff_status == "Đạt" and csvc_status == "Đạt",
    }


# BAI_13B_12_V2_4_4_4_TH02_REUSE_PRIOR_DATA
# === BAI_13B_12_V2_4_4_4_TH02_REUSE_PRIOR_DATA_END ===

# === BAI_13B_12_V2_4_4_5_TH02_DIAGNOSTIC_SOURCE_START ===
# Sửa theo kết quả chẩn đoán thực tế Xã Nghi Lộc:
# - 5/5 trường TH có dữ liệu mạng lưới năm gần nhất và national_standard=1.
# - 5/5 có TH_01_GV (ít nhất năm gần nhất), nhưng 4/5 chưa từng có TH_01_CSVC.
# - Vì vậy không buộc nhập lại checklist mới chỉ để kết luận TH-02.
#
# Nguyên tắc fallback:
# 1) Cờ PCGD tường minh trong TH_01_GV/TH_01_CSVC luôn ưu tiên cao nhất.
#    Có cờ Không => Không đảm bảo, không bị fallback ghi đè.
# 2) Nếu chỉ thiếu các cờ định tính mới, trường đã có national_standard=1 trong
#    dữ liệu mạng lưới được dùng như minh chứng dự phòng cho điều kiện đội ngũ/
#    CSVC. Tỷ lệ phòng/lớp và dữ liệu giáo viên/lớp vẫn kiểm tra riêng.
# 3) Nếu không có national_standard=1 và cũng thiếu cờ chi tiết thì vẫn giữ
#    Chưa đủ dữ liệu; không suy diễn.
# 4) Chỉ đọc database, không INSERT/UPDATE/DELETE.

_b2445_previous_staff_status_for_school = _b2443_staff_status_for_school
_b2445_previous_csvc_status_for_school = _b2443_csvc_status_for_school


def _b2445_boolish(value: Any) -> bool | None:
    if value is None or value == "":
        return None
    if value is True:
        return True
    if value is False:
        return False
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = None
    if number is not None:
        if abs(number - 1.0) < 1e-9:
            return True
        if abs(number) < 1e-9:
            return False
    text = _norm(value)
    if text in {"CO", "YES", "TRUE", "DAT", "DAT CHUAN", "DAM BAO"}:
        return True
    if text in {"KHONG", "NO", "FALSE", "KHONG DAT", "CHUA DAT", "KHONG DAM BAO"}:
        return False
    return None


def _b2445_network_national_standard(
    db: Session,
    *,
    school_id: int,
    school_year_id: int,
) -> bool | None:
    network = _network_reference_data(
        db,
        school_id=int(school_id),
        level="TH",
        target_year_id=int(school_year_id),
    )
    return _b2445_boolish(network.get("national_standard"))


def _b2445_teacher_total(
    db: Session,
    *,
    school_id: int,
    school_year_id: int,
    saved_staff: dict[str, Any],
) -> float | None:
    value = _b2443_number(saved_staff, "teacher_total")
    if value is not None and value > 0:
        return value
    network = _network_reference_data(
        db,
        school_id=int(school_id),
        level="TH",
        target_year_id=int(school_year_id),
    )
    try:
        value = float(network.get("teachers"))
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _b2443_staff_status_for_school(
    db: Session,
    *,
    school_id: int,
    school_year_id: int,
    grades: dict[int, list[int]],
    saved_staff: dict[str, Any],
    saved_csvc: dict[str, Any],
) -> tuple[str, list[str]]:
    # Trước hết dùng toàn bộ logic V2.4.4.4.
    status, missing = _b2445_previous_staff_status_for_school(
        db,
        school_id=int(school_id),
        school_year_id=int(school_year_id),
        grades=grades,
        saved_staff=saved_staff,
        saved_csvc=saved_csvc,
    )
    if status != "Chưa xác nhận":
        return status, missing

    # Một cờ tường minh "Không" luôn thắng fallback.
    explicit_flags = [
        _b2443_flag(saved_staff, key)
        for key in _B2441_STAFF_VERIFY_KEYS
    ]
    if any(flag is False for flag in explicit_flags):
        return "Chưa đạt", [f"school_id={school_id}: có điều kiện đội ngũ được xác nhận Không"]

    # Chỉ fallback khi dữ liệu mạng lưới chính thức của trường ghi nhận
    # national_standard=1.
    if _b2445_network_national_standard(
        db,
        school_id=int(school_id),
        school_year_id=int(school_year_id),
    ) is not True:
        return status, missing

    # Vẫn kiểm tra tối thiểu giáo viên/lớp, không dùng national_standard để che
    # một thiếu hụt số lượng rõ ràng.
    class_total = _class_count_with_network(
        db,
        school_id=int(school_id),
        school_year_id=int(school_year_id),
        grades=grades,
        level="TH",
    )
    teacher_total = _b2445_teacher_total(
        db,
        school_id=int(school_id),
        school_year_id=int(school_year_id),
        saved_staff=saved_staff,
    )
    if class_total <= 0 or teacher_total is None:
        return status, missing
    if teacher_total + 1e-9 < float(class_total):
        return "Chưa đạt", [f"school_id={school_id}: số giáo viên thấp hơn số lớp"]

    # Người theo dõi PCGD: cờ tường minh nếu có; nếu chưa có thì dùng chính
    # việc trường đã vận hành dữ liệu PCGD/tài khoản trường làm minh chứng.
    tracker = _b2443_flag(saved_staff, "pcgd_tracker_assigned")
    if tracker is False:
        return "Chưa đạt", [f"school_id={school_id}: chưa phân công người theo dõi PCGD-XMC"]
    if tracker is None:
        tracker = bool(
            saved_staff
            or saved_csvc
            or _b2443_school_has_pcgd_responsible_account(db, int(school_id))
        )
    if not tracker:
        return status, missing

    return "Đạt", []


def _b2445_room_ratio(
    db: Session,
    *,
    school_id: int,
    school_year_id: int,
    grades: dict[int, list[int]],
    saved: dict[str, Any],
) -> bool | None:
    values = _b2444_currentize_csvc_values(
        db,
        school_id=int(school_id),
        school_year_id=int(school_year_id),
        grades=grades,
        saved=saved,
    )
    classes = _b2443_number(values, "class_total")
    rooms = [
        _b2443_number(values, key)
        for key in (
            "room_permanent",
            "room_semi_permanent",
            "room_temporary",
            "room_rent_borrow",
        )
    ]
    if classes is None or classes <= 0 or all(value is None for value in rooms):
        return None
    return (sum(value or 0.0 for value in rooms) / classes) + 1e-9 >= 0.7


def _b2443_csvc_status_for_school(
    db: Session,
    *,
    school_id: int,
    school_year_id: int,
    grades: dict[int, list[int]],
    saved: dict[str, Any],
) -> tuple[str, list[str]]:
    # Trước hết dùng toàn bộ logic V2.4.4.3/V2.4.4.4.
    status, missing = _b2445_previous_csvc_status_for_school(
        db,
        school_id=int(school_id),
        school_year_id=int(school_year_id),
        grades=grades,
        saved=saved,
    )
    if status != "Chưa xác nhận":
        return status, missing

    # Cờ tường minh "Không" luôn thắng.
    explicit_flags = [
        _b2443_flag(saved, key)
        for key in _B2441_FACILITY_VERIFY_KEYS
    ]
    if any(flag is False for flag in explicit_flags):
        return "Chưa đạt", [f"school_id={school_id}: có điều kiện CSVC/TBDH được xác nhận Không"]

    if _b2445_network_national_standard(
        db,
        school_id=int(school_id),
        school_year_id=int(school_year_id),
    ) is not True:
        return status, missing

    # Tỷ lệ phòng/lớp là chỉ tiêu định lượng bắt buộc, vẫn kiểm tra riêng.
    room_ok = _b2445_room_ratio(
        db,
        school_id=int(school_id),
        school_year_id=int(school_year_id),
        grades=grades,
        saved=saved,
    )
    if room_ok is False:
        return "Chưa đạt", [f"school_id={school_id}: tỷ lệ phòng/lớp dưới 0,7"]
    if room_ok is None:
        return status, missing

    return "Đạt", []


# BAI_13B_12_V2_4_4_5_TH02_DIAGNOSTIC_SOURCE
# === BAI_13B_12_V2_4_4_5_TH02_DIAGNOSTIC_SOURCE_END ===
