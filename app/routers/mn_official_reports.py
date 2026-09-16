from __future__ import annotations

import io
import re
import unicodedata
from copy import copy
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db


router = APIRouter(tags=["Báo cáo Mầm non mẫu mới"])
templates = Jinja2Templates(directory="app/templates")

APP_DIR = Path(__file__).resolve().parents[1]
REPORT_TEMPLATE_DIR = APP_DIR / "report_templates"
TE_TEMPLATE_PATH = REPORT_TEMPLATE_DIR / "MN-01-TE_2026.xlsx"
GV_TEMPLATE_PATH = REPORT_TEMPLATE_DIR / "MN-01-GV_BGD_2026.xlsx"

ALLOWED_ROLES = {"ADMIN", "SO", "PHONG_BAN", "XA", "TRUONG"}
PROVINCE_ROLES = {"ADMIN", "SO", "PHONG_BAN"}
# === BAI_13B_12_V2_4_3_4_LEGACY_REDIRECT ===
OLD_TO_NEW = {
    "PCGD_MN_M1_2025": "mn-01-te",
    "PCGD_MN_02_2025": "mn-02",
    "PCGD_MN_01_GV_2025": "mn-01-gv",
    "PCGD_MN_01_CSVC_2025": "mn-01-csvc",
    "PCGD_MN_TAICHINH_2025": "mn-tc",
}


def _auth_user(request: Request) -> dict[str, Any]:
    return dict(request.scope.get("auth_user") or {})


def _role(request: Request) -> str:
    return str(_auth_user(request).get("role_code") or "").strip().upper()


def _forbidden() -> RedirectResponse:
    return RedirectResponse(url="/?status=forbidden", status_code=303)


def _maps(db: Session, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    return [dict(row) for row in db.execute(text(sql), params or {}).mappings().all()]


def _one(db: Session, sql: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
    row = db.execute(text(sql), params or {}).mappings().first()
    return dict(row) if row is not None else None


def _table_exists(db: Session, table_name: str) -> bool:
    value = db.execute(
        text("SELECT 1 FROM sqlite_master WHERE type='table' AND name=:name LIMIT 1"),
        {"name": table_name},
    ).scalar()
    return value is not None


def _norm(value: Any) -> str:
    raw = " ".join(str(value or "").strip().split())
    normalized = unicodedata.normalize("NFD", raw)
    without_marks = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^A-Z0-9]+", "_", without_marks.upper()).strip("_")


def _as_int(value: Any) -> int | None:
    try:
        if value is None or str(value).strip() == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    n = _norm(value)
    if n in {"1", "TRUE", "YES", "CO", "CÓ", "X"}:
        return True
    if n in {"0", "FALSE", "NO", "KHONG", "KHÔNG"}:
        return False
    return None


def _parse_birth_year(value: Any) -> int | None:
    if value is None:
        return None
    if hasattr(value, "year"):
        try:
            return int(value.year)
        except Exception:
            pass
    s = str(value).strip()
    if not s:
        return None
    for pattern in (r"^(\d{4})-", r"/(\d{4})$", r"^(\d{4})$"):
        match = re.search(pattern, s)
        if match:
            try:
                return int(match.group(1))
            except Exception:
                return None
    return None


def _report_year_start(code: str) -> int:
    match = re.search(r"(20\d{2})", str(code or ""))
    if match:
        return int(match.group(1))
    return date.today().year


def _school_years(db: Session) -> list[dict[str, Any]]:
    return _maps(db, "SELECT id, code FROM school_years ORDER BY code DESC, id DESC")


def _communes(db: Session) -> list[dict[str, Any]]:
    return _maps(db, "SELECT id, code, name FROM communes ORDER BY name, id")


def _school_row(db: Session, school_id: int) -> dict[str, Any] | None:
    return _one(db, "SELECT id, code, name, commune_id FROM schools WHERE id=:id", {"id": school_id})


def _commune_row(db: Session, commune_id: int) -> dict[str, Any] | None:
    return _one(db, "SELECT id, code, name FROM communes WHERE id=:id", {"id": commune_id})


def _is_mn_name(name: Any) -> bool:
    n = _norm(name)
    tokens = (
        "MAM_NON", "MAU_GIAO", "NHOM_TRE", "LOP_MAM_NON",
        "GDMN", "GIAO_DUC_MAM_NON",
    )
    return any(token in n for token in tokens)


def _mn_school_rows(db: Session, year_id: int | None, commune_id: int | None) -> list[dict[str, Any]]:
    params: dict[str, Any] = {}
    where = []
    if commune_id is not None:
        where.append("s.commune_id=:commune_id")
        params["commune_id"] = int(commune_id)
    sql = "SELECT s.id, s.code, s.name, s.commune_id FROM schools AS s"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY s.name, s.id"
    rows = _maps(db, sql, params)

    summary_ids: set[int] = set()
    if year_id is not None and _table_exists(db, "school_staff_year_summaries"):
        q = "SELECT DISTINCT school_id FROM school_staff_year_summaries WHERE school_year_id=:year_id"
        p: dict[str, Any] = {"year_id": int(year_id)}
        if commune_id is not None:
            q = (
                "SELECT DISTINCT ss.school_id FROM school_staff_year_summaries ss "
                "JOIN schools s ON s.id=ss.school_id "
                "WHERE ss.school_year_id=:year_id AND s.commune_id=:commune_id"
            )
            p["commune_id"] = int(commune_id)
        summary_ids = {int(r["school_id"]) for r in _maps(db, q, p) if r.get("school_id") is not None}

    result = [row for row in rows if int(row["id"]) in summary_ids or _is_mn_name(row.get("name"))]
    return result


def _build_scope(
    db: Session,
    request: Request,
    school_year_id: int | None,
    commune_id: int | None,
    school_id: int | None,
) -> dict[str, Any] | None:
    user = _auth_user(request)
    role = _role(request)
    if role not in ALLOWED_ROLES:
        return None

    years = _school_years(db)
    selected_year_id = _as_int(school_year_id)
    if selected_year_id not in {int(y["id"]) for y in years}:
        selected_year_id = int(years[0]["id"]) if years else None
    selected_year = next((y for y in years if selected_year_id is not None and int(y["id"]) == selected_year_id), None)

    selected_commune_id = _as_int(commune_id)
    selected_school_id = _as_int(school_id)

    user_commune_id = _as_int(user.get("commune_id"))
    user_school_id = _as_int(user.get("school_id"))

    if role == "XA":
        selected_commune_id = user_commune_id
    elif role == "TRUONG":
        selected_school_id = user_school_id
        if selected_school_id is not None:
            sr = _school_row(db, selected_school_id)
            selected_commune_id = _as_int((sr or {}).get("commune_id"))

    if selected_school_id is not None:
        sr = _school_row(db, selected_school_id)
        if sr is None:
            selected_school_id = None
        else:
            school_commune_id = _as_int(sr.get("commune_id"))
            if role == "XA" and user_commune_id is not None and school_commune_id != user_commune_id:
                selected_school_id = None
            elif selected_commune_id is not None and school_commune_id != selected_commune_id:
                selected_school_id = None
            else:
                selected_commune_id = school_commune_id if role == "TRUONG" else selected_commune_id

    all_communes = _communes(db)
    if role == "XA":
        communes = [c for c in all_communes if user_commune_id is not None and int(c["id"]) == user_commune_id]
    elif role == "TRUONG":
        communes = [c for c in all_communes if selected_commune_id is not None and int(c["id"]) == selected_commune_id]
    else:
        communes = all_communes

    schools = _mn_school_rows(db, selected_year_id, selected_commune_id)
    if role == "TRUONG" and user_school_id is not None:
        own = _school_row(db, user_school_id)
        schools = [own] if own else []

    valid_school_ids = {int(s["id"]) for s in schools if s}
    if selected_school_id is not None and selected_school_id not in valid_school_ids:
        if role == "TRUONG":
            pass
        else:
            selected_school_id = None

    selected_commune = next((c for c in all_communes if selected_commune_id is not None and int(c["id"]) == selected_commune_id), None)
    selected_school = _school_row(db, selected_school_id) if selected_school_id is not None else None

    if selected_school:
        scope_label = str(selected_school.get("name") or "Trường Mầm non")
    elif selected_commune:
        scope_label = str(selected_commune.get("name") or "Xã/phường")
    else:
        scope_label = "Toàn tỉnh"

    return {
        "user": user,
        "role": role,
        "years": years,
        "selected_year_id": selected_year_id,
        "selected_year": selected_year,
        "communes": communes,
        "schools": schools,
        "selected_commune_id": selected_commune_id,
        "selected_commune": selected_commune,
        "selected_school_id": selected_school_id,
        "selected_school": selected_school,
        "scope_label": scope_label,
        "lock_commune": role in {"XA", "TRUONG"},
        "lock_school": role == "TRUONG",
    }


# === BAI_13B_11_15_2_4_6_MN_OFFICIAL_SOURCE_START ===
def _query_te_people(db: Session, scope: dict[str, Any]) -> list[dict[str, Any]]:
    year_id = scope.get("selected_year_id")
    if year_id is None:
        return []
    if not all(_table_exists(db, name) for name in (
        "survey_people", "survey_forms", "survey_batches", "survey_person_year_records"
    )):
        return []

    where = ["sb.school_year_id=:year_id", "COALESCE(sp.is_active,1)=1"]
    params: dict[str, Any] = {"year_id": int(year_id)}

    # Khi chọn một trường, lấy toàn bộ trẻ có hồ sơ năm học tại trường đó,
    # kể cả trẻ cư trú ở xã/phường khác. Khi không chọn trường mới khóa theo hộ cư trú của xã.
    if scope.get("selected_school_id") is not None:
        where.append("spr.school_id=:school_id")
        params["school_id"] = int(scope["selected_school_id"])
    elif scope.get("selected_commune_id") is not None:
        where.append("sb.commune_id=:commune_id")
        params["commune_id"] = int(scope["selected_commune_id"])

    sql = f"""
        SELECT
            sp.id AS person_id,
            sp.date_of_birth,
            sp.gender,
            sp.ethnic_group,
            sp.residency_status,
            spr.learning_status,
            spr.school_id,
            spr.school_name_reported,
            spr.completed_preschool_5,
            spr.disability_access_education,
            spr.disability_can_learn,
            spr.attends_two_sessions_per_day,
            spr.prepared_vietnamese,
            sb.commune_id AS home_commune_id,
            school.commune_id AS school_commune_id
        FROM survey_people AS sp
        JOIN survey_forms AS sf ON sf.household_id=sp.household_id
        JOIN survey_batches AS sb ON sb.id=sf.survey_batch_id
        LEFT JOIN survey_person_year_records AS spr
          ON spr.survey_person_id=sp.id
         AND spr.school_year_id=sb.school_year_id
         AND spr.survey_form_id=sf.id
        LEFT JOIN schools AS school ON school.id=spr.school_id
        WHERE {' AND '.join(where)}
        ORDER BY sp.id, sf.id
    """
    rows = _maps(db, sql, params)

    # Tránh đếm trùng một đối tượng khi có dữ liệu lịch sử/phiếu lặp trong cùng phạm vi.
    dedup: dict[int, dict[str, Any]] = {}
    for row in rows:
        pid = _as_int(row.get("person_id"))
        if pid is None:
            continue
        current = dedup.get(pid)
        if current is None or (current.get("learning_status") is None and row.get("learning_status") is not None):
            dedup[pid] = row
    return list(dedup.values())

def _te_metrics(rows: list[dict[str, Any]], year_code: str) -> dict[str, Any]:
    ref_year = _report_year_start(year_code)
    metric_names = (
        "total", "girls", "ethnic", "attending", "attending_girls",
        "attending_ethnic", "prepared_vi", "local_school", "outside_school",
        "moved_out", "moved_in", "completed5", "two_sessions", "disabled_capable", "disabled_access_v246",
    )
    metrics = {name: {age: 0 for age in range(7)} for name in metric_names}
    unknown_birth = 0

    for row in rows:
        birth_year = _parse_birth_year(row.get("date_of_birth"))
        if birth_year is None:
            unknown_birth += 1
            continue
        age = ref_year - birth_year
        if age < 0 or age > 6:
            continue

        residency = _norm(row.get("residency_status"))
        moved_out = "CHUYEN_DI" in residency
        moved_in = "CHUYEN_DEN" in residency
        if moved_out:
            metrics["moved_out"][age] += 1
        if moved_in:
            metrics["moved_in"][age] += 1

        # Tổng trẻ đang thuộc phạm vi: không đưa bản ghi đã chuyển đi vào tổng hiện có.
        if moved_out:
            continue

        metrics["total"][age] += 1
        gender = _norm(row.get("gender"))
        is_girl = gender in {"NU", "FEMALE"}
        if is_girl:
            metrics["girls"][age] += 1

        ethnic = _norm(row.get("ethnic_group"))
        is_ethnic = bool(ethnic) and ethnic != "KINH"
        if is_ethnic:
            metrics["ethnic"][age] += 1

        learning = _norm(row.get("learning_status"))
        attending = learning in {"DANG_HOC", "DANGHOC"} or ("DANG" in learning and "HOC" in learning)
        # === BAI_13B_11_15_2_4_6_DISABILITY_METRICS ===
        _v246_can_raw = _as_bool(row.get("disability_can_learn"))
        _v246_access_raw = _as_bool(row.get("disability_access_education"))
        _v246_can = (
            _v246_can_raw is True
            or (
                _v246_can_raw is None
                and _v246_access_raw is True
            )
        )
        if _v246_can:
            metrics["disabled_capable"][age] += 1
            if _v246_access_raw is True:
                metrics["disabled_access_v246"][age] += 1

        if attending:
            metrics["attending"][age] += 1
            if is_girl:
                metrics["attending_girls"][age] += 1
            if is_ethnic:
                metrics["attending_ethnic"][age] += 1
                if _as_bool(row.get("prepared_vietnamese")) is True:
                    metrics["prepared_vi"][age] += 1

            home_commune = _as_int(row.get("home_commune_id"))
            school_commune = _as_int(row.get("school_commune_id"))
            if school_commune is not None and home_commune is not None:
                if school_commune == home_commune:
                    metrics["local_school"][age] += 1
                else:
                    metrics["outside_school"][age] += 1

        if attending and _as_bool(row.get("attends_two_sessions_per_day")) is True:
            metrics["two_sessions"][age] += 1

        if _as_bool(row.get("completed_preschool_5")) is True:
            metrics["completed5"][age] += 1

    return {"metrics": metrics, "unknown_birth": unknown_birth, "ref_year": ref_year}

def _sum_0_5(values: dict[int, int]) -> int:
    return sum(int(values.get(age, 0) or 0) for age in range(6))


def _te_context(scope: dict[str, Any], rows: list[dict[str, Any]], calc: dict[str, Any]) -> dict[str, Any]:
    year_code = str((scope.get("selected_year") or {}).get("code") or "")
    m = calc["metrics"]
    warnings = [
        "Mẫu MN-01-TE mới đã được thay đúng file gốc. Các chỉ tiêu chỉ được tự điền khi hệ thống có trường dữ liệu xác định rõ ràng.",
        "Hệ thống đã có dữ liệu cấu trúc cho học 2 buổi/ngày. Các chỉ tiêu còn chưa đủ nguồn chắc chắn như khả năng học tập/tiếp cận giáo dục của trẻ khuyết tật, số phải huy động, tử vong và dữ liệu làm căn cứ hoàn thành chương trình theo năm trước vẫn được giữ trống, không tự suy đoán thành 0.",
    ]
    if calc.get("unknown_birth"):
        warnings.append(f"Có {calc['unknown_birth']} đối tượng chưa xác định được năm sinh nên không đưa vào cột độ tuổi.")
    if not rows:
        warnings.append("Chưa tìm thấy dữ liệu điều tra trong phạm vi/năm học đang chọn.")

    return {
        **scope,
        "report_code": "MN-01-TE",
        "report_title": "MN-01-TE – Thống kê trẻ em Mầm non theo độ tuổi",
        "export_path": "/bao-cao/mn-01-te/xuat-excel",
        "summary_cards": [
            ("Trẻ 0–5 tuổi", _sum_0_5(m["total"])),
            ("Đang học 0–5", _sum_0_5(m["attending"])),
            ("Trẻ 5 tuổi", int(m["total"].get(5, 0))),
            ("5 tuổi đang học", int(m["attending"].get(5, 0))),
        ],
        "warnings": warnings,
        "year_code": year_code,
        "data_rows": len(rows),
    }


def _query_gv_rows(db: Session, scope: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[int, dict[str, Any]]]:
    year_id = scope.get("selected_year_id")
    if year_id is None or not all(_table_exists(db, name) for name in (
        "staff_year_records", "staff_members", "schools"
    )):
        return [], {}

    mn_schools = _mn_school_rows(db, int(year_id), scope.get("selected_commune_id"))
    if scope.get("selected_school_id") is not None:
        school_ids = {int(scope["selected_school_id"])}
    else:
        school_ids = {int(s["id"]) for s in mn_schools}
    if not school_ids:
        return [], {}

    placeholders = ",".join(str(int(x)) for x in sorted(school_ids))
    rows = _maps(
        db,
        f"""
        SELECT syr.*, sm.full_name, sm.ethnic_group, sm.is_active AS member_active,
               s.name AS school_name, s.commune_id
        FROM staff_year_records AS syr
        JOIN staff_members AS sm ON sm.id=syr.staff_member_id
        JOIN schools AS s ON s.id=syr.school_id
        WHERE syr.school_year_id=:year_id
          AND syr.school_id IN ({placeholders})
          AND COALESCE(syr.is_active,1)=1
          AND COALESCE(sm.is_active,1)=1
          AND COALESCE(syr.status_code,'DANG_LAM_VIEC')='DANG_LAM_VIEC'
        ORDER BY s.name, sm.full_name, syr.id
        """,
        {"year_id": int(year_id)},
    )

    summaries: dict[int, dict[str, Any]] = {}
    if _table_exists(db, "school_staff_year_summaries"):
        for row in _maps(
            db,
            f"SELECT * FROM school_staff_year_summaries WHERE school_year_id=:year_id AND school_id IN ({placeholders})",
            {"year_id": int(year_id)},
        ):
            sid = _as_int(row.get("school_id"))
            if sid is not None:
                summaries[sid] = row

    return rows, summaries


def _gv_age(value: Any) -> str | None:
    n = _norm(value)
    if not n or "KHONG_XAC_DINH" in n or "CHUA_XAC_DINH" in n:
        return None
    if any(token in n for token in ("3_4", "3_DEN_4", "3_4_TUOI", "MAU_GIAO_3_4")):
        return "3_4"
    if any(token in n for token in ("5_TUOI", "MAU_GIAO_5", "LOP_5", "5_6")):
        return "5"
    return None


def _is_contract(value: Any) -> bool:
    n = _norm(value)
    return "HOP_DONG" in n or n in {"HD", "CONTRACT"}


def _qual_bucket(row: dict[str, Any]) -> str | None:
    standard = _norm(row.get("qualification_standard"))
    if standard and "CHUA_XAC_DINH" not in standard:
        if "TREN" in standard:
            return "above"
        if "DAT" in standard and "CHUA_DAT" not in standard and "KHONG_DAT" not in standard:
            return "standard"
        if "CHUA_DAT" in standard or "KHONG_DAT" in standard:
            return "below"

    level = _norm(row.get("qualification_level"))
    if any(token in level for token in ("DAI_HOC", "THAC_SI", "TIEN_SI", "SAU_DAI_HOC")):
        return "above"
    if "CAO_DANG" in level:
        return "standard"
    if any(token in level for token in ("TRUNG_CAP", "SO_CAP")):
        return "below"
    return None


def _professional_pass(row: dict[str, Any]) -> bool | None:
    n = _norm(row.get("professional_standard"))
    if not n or "CHUA_DANH_GIA" in n or "CHUA_XAC_DINH" in n:
        return None
    if "CHUA_DAT" in n or "KHONG_DAT" in n:
        return False
    return True


def _is_independent(name: Any, summary: dict[str, Any] | None) -> bool:
    if summary and _norm(summary.get("institution_group")) == "CO_SO_GDMN_DOC_LAP":
        return True
    n = _norm(name)
    return any(token in n for token in ("NHOM_TRE", "LOP_MAM_NON", "CO_SO_GDMN", "GDMN_DOC_LAP"))


def _empty_gv_metric() -> dict[str, Any]:
    return {
        "staff": 0, "contract_staff": 0, "managers": 0, "teachers": 0, "employees": 0,
        "classes_total": 0,
        "age": {
            "3_4": {"classes": 0, "teachers": 0, "contract": 0, "policy": 0, "standard": 0, "above": 0, "professional_pass": 0},
            "5": {"classes": 0, "teachers": 0, "contract": 0, "policy": 0, "standard": 0, "above": 0, "professional_pass": 0},
        },
        "unknown_age_teachers": 0, "unknown_qual_teachers": 0, "unknown_prof_teachers": 0,
    }


def _gv_school_metrics(rows: list[dict[str, Any]], summaries: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[int, list[dict[str, Any]]] = {}
    school_names: dict[int, str] = {}
    for row in rows:
        sid = _as_int(row.get("school_id"))
        if sid is None:
            continue
        grouped.setdefault(sid, []).append(row)
        school_names[sid] = str(row.get("school_name") or f"Trường {sid}")

    # Có thể có trường chỉ có số lớp nhưng chưa có nhân sự.
    for sid in summaries:
        grouped.setdefault(sid, [])
        if sid not in school_names:
            school_names[sid] = f"Trường {sid}"

    result: list[dict[str, Any]] = []
    for sid in sorted(grouped, key=lambda x: school_names.get(x, "")):
        metric = _empty_gv_metric()
        summary = summaries.get(sid) or {}
        metric["classes_total"] = int(summary.get("total_groups_classes") or 0)
        metric["age"]["3_4"]["classes"] = int(summary.get("preschool_classes_3_4") or 0)
        metric["age"]["5"]["classes"] = int(summary.get("preschool_classes_5") or 0)

        for row in grouped[sid]:
            metric["staff"] += 1
            if _is_contract(row.get("employment_type")):
                metric["contract_staff"] += 1
            pos = _norm(row.get("position_group"))
            if pos == "CBQL":
                metric["managers"] += 1
            elif pos == "NHAN_VIEN":
                metric["employees"] += 1
            elif pos == "GIAO_VIEN":
                metric["teachers"] += 1
                age_key = _gv_age(row.get("teaching_age_group"))
                if age_key is None:
                    metric["unknown_age_teachers"] += 1
                    continue
                age_metric = metric["age"][age_key]
                age_metric["teachers"] += 1
                if _is_contract(row.get("employment_type")):
                    age_metric["contract"] += 1
                if _as_bool(row.get("receives_policy")) is True:
                    age_metric["policy"] += 1
                qual = _qual_bucket(row)
                if qual == "standard":
                    age_metric["standard"] += 1
                elif qual == "above":
                    age_metric["above"] += 1
                elif qual is None:
                    metric["unknown_qual_teachers"] += 1
                prof = _professional_pass(row)
                if prof is True:
                    age_metric["professional_pass"] += 1
                elif prof is None:
                    metric["unknown_prof_teachers"] += 1

        result.append({
            "school_id": sid,
            "name": school_names.get(sid, f"Trường {sid}"),
            "independent": _is_independent(school_names.get(sid), summary),
            "metric": metric,
        })
    return result


def _aggregate_gv(items: list[dict[str, Any]]) -> dict[str, Any]:
    total = _empty_gv_metric()
    for item in items:
        m = item["metric"]
        for key in ("staff", "contract_staff", "managers", "teachers", "employees", "classes_total", "unknown_age_teachers", "unknown_qual_teachers", "unknown_prof_teachers"):
            total[key] += int(m.get(key, 0) or 0)
        for age in ("3_4", "5"):
            for key in total["age"][age]:
                total["age"][age][key] += int(m["age"][age].get(key, 0) or 0)
    return total


def _gv_context(scope: dict[str, Any], items: list[dict[str, Any]]) -> dict[str, Any]:
    total = _aggregate_gv(items)
    warnings = [
        "MN-01-GV BGD lấy số liệu từ phân hệ Đội ngũ và cấu hình số lớp theo đúng năm học/phạm vi.",
    ]
    if total["unknown_age_teachers"]:
        warnings.append(f"Có {total['unknown_age_teachers']} giáo viên chưa xác định nhóm 3–4 tuổi/5 tuổi; các cột theo nhóm tuổi chỉ cộng phần đã phân loại.")
    if total["unknown_qual_teachers"]:
        warnings.append(f"Có {total['unknown_qual_teachers']} giáo viên chưa đủ thông tin chuẩn trình độ đào tạo.")
    if total["unknown_prof_teachers"]:
        warnings.append(f"Có {total['unknown_prof_teachers']} giáo viên chưa đánh giá chuẩn nghề nghiệp.")
    if not items:
        warnings.append("Chưa tìm thấy dữ liệu đội ngũ Mầm non trong phạm vi/năm học đang chọn.")

    return {
        **scope,
        "report_code": "MN-01-GV",
        "report_title": "MN-01-GV – Thống kê đội ngũ CBQL, giáo viên, nhân viên",
        "export_path": "/bao-cao/mn-01-gv-bgd/xuat-excel",
        "summary_cards": [
            ("Cơ sở/trường", len(items)),
            ("Tổng đội ngũ", total["staff"]),
            ("Giáo viên", total["teachers"]),
            ("Tổng lớp", total["classes_total"]),
        ],
        "warnings": warnings,
        "year_code": str((scope.get("selected_year") or {}).get("code") or ""),
        "data_rows": len(items),
    }


def _content_disposition(filename: str) -> dict[str, str]:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", filename)
    return {"Content-Disposition": f'attachment; filename="{safe}"'}


def _fill_te_workbook(scope: dict[str, Any], calc: dict[str, Any]) -> bytes:
    from openpyxl import load_workbook

    wb = load_workbook(TE_TEMPLATE_PATH)
    ws = wb["Thống kê trẻ em từ 0 đến 5 tuổi"]
    year_code = str((scope.get("selected_year") or {}).get("code") or "")
    commune_name = str((scope.get("selected_commune") or {}).get("name") or scope.get("scope_label") or "Toàn tỉnh")
    ws["B1"] = f"Xã: {commune_name}"
    ws["B2"] = "Tỉnh: Nghệ An"
    ws["D2"] = f"Thời điểm: tháng {date.today().month:02d} năm {calc['ref_year']}"

    metrics = calc["metrics"]
    row_metric = {
        6: "total",
        7: "girls",
        8: "ethnic",
        13: "attending",
        14: "local_school",
        15: "outside_school",
        17: "attending_girls",
        18: "attending_ethnic",
        19: "prepared_vi",
        24: "moved_out",
        25: "moved_in",
    }
    age_cols = {0: "F", 1: "G", 2: "H", 3: "I", 4: "J", 5: "K", 6: "L"}
    for row_no, metric_name in row_metric.items():
        vals = metrics[metric_name]
        for age, col in age_cols.items():
            ws[f"{col}{row_no}"] = int(vals.get(age, 0) or 0)
        ws[f"M{row_no}"] = _sum_0_5(vals)

    # Hoàn thành CT GDMN 5 tuổi: chỉ điền đúng trường dữ liệu completed_preschool_5.
    completed = metrics["completed5"]
    for age in (4, 5, 6):
        col = age_cols[age]
        ws[f"{col}27"] = int(completed.get(age, 0) or 0)
    ws["M27"] = int(completed.get(4, 0) or 0) + int(completed.get(5, 0) or 0)

    # Tiêu chí: điền số lượng chắc chắn, không tự tính tỷ lệ khi thiếu mẫu số chính thức.
    ws["E35"] = int(metrics["attending"].get(5, 0) or 0)
    ws["E38"] = int(metrics["completed5"].get(5, 0) or 0)
    ws["E40"] = int(metrics["attending"].get(3, 0) or 0) + int(metrics["attending"].get(4, 0) or 0)


        # === BAO_CAO_MN_MAU_MOI_V1_3_TY_LE_TRUC_TIEP START ===
    # V1.3:
    # - Ghi giá trị tỷ lệ trực tiếp, không phụ thuộc Excel recalculation.
    # - Dò dòng theo nhãn của mẫu, không phụ thuộc số dòng cố định.
    # - Nếu mẫu số chưa có/không hợp lệ thì giữ ô trống.

    def _v13_number(value):
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, (int, float)):
            return float(value)
        return None

    def _v13_pct100(numerator, denominator):
        n = _v13_number(numerator)
        d = _v13_number(denominator)

        if n is None or d is None or d <= 0:
            return None

        return round(n / d * 100.0, 2)

    def _v13_ratio_decimal(numerator, denominator):
        n = _v13_number(numerator)
        d = _v13_number(denominator)

        if n is None or d is None or d <= 0:
            return None

        return n / d

    # === BAO_CAO_MN_MAU_MOI_V1_3_2_FIX_NORM_TEXT ===
    def _v13_norm_text(value):
        import unicodedata

        text_value = str(
            value or ""
        )

        text_value = unicodedata.normalize(
            "NFD",
            text_value,
        )

        text_value = "".join(
            char
            for char in text_value
            if unicodedata.category(char) != "Mn"
        )

        return " ".join(
            text_value.upper().split()
        )

    def _v13_row_contains(*parts, start_row=1):
        expected = [
            _v13_norm_text(part)
            for part in parts
            if str(part or "").strip()
        ]

        for row_no in range(
            max(1, int(start_row)),
            ws.max_row + 1,
        ):
            row_text = " ".join(
                str(
                    ws.cell(
                        row=row_no,
                        column=col_no,
                    ).value
                    or ""
                )
                for col_no in range(
                    1,
                    min(ws.max_column, 16) + 1,
                )
            )

            normalized = _v13_norm_text(row_text)

            if all(
                part in normalized
                for part in expected
            ):
                return row_no

        return None

    def _v13_header_column(
        row_no,
        label,
    ):
        expected = _v13_norm_text(label)

        if not row_no:
            return None

        for col_no in range(
            1,
            ws.max_column + 1,
        ):
            value = ws.cell(
                row=row_no,
                column=col_no,
            ).value

            if (
                expected
                in _v13_norm_text(value or "")
            ):
                return col_no

        return None

    def _v13_cell(row_no, col_letter):
        if not row_no or not col_letter:
            return None

        return ws[
            f"{col_letter}{row_no}"
        ].value

    def _v13_sum_ages(
        row_no,
        ages,
    ):
        if not row_no:
            return None

        values = []

        for age in ages:
            col = age_cols.get(age)

            if not col:
                continue

            value = _v13_number(
                ws[
                    f"{col}{row_no}"
                ].value
            )

            if value is not None:
                values.append(value)

        if not values:
            return None

        return sum(values)

    # ----------------------------------------------------------
    # A. XÁC ĐỊNH DÒNG CỦA BẢNG CHÍNH
    # ----------------------------------------------------------
    total_children_row = _v13_row_contains(
        "Tổng số trẻ trong độ tuổi"
    )

    disability_total_row = _v13_row_contains(
        "Trẻ khuyết tật trong độ tuổi",
        "Tổng số",
    )

    disability_access_row = _v13_row_contains(
        "Số trẻ được tiếp cận giáo dục"
    )

    must_mobilize_row = _v13_row_contains(
        "Số trẻ phải huy động"
    )

    attending_row = _v13_row_contains(
        "Số trẻ đến trường"
    )

    mobilization_ratio_row = _v13_row_contains(
        "Tỉ lệ huy động"
    )

    two_sessions_row = _v13_row_contains(
        "Số trẻ học 2 buổi/ngày"
    )

    two_sessions_ratio_row = _v13_row_contains(
        "Tỉ lệ trẻ học 2 buổi"
    )

    completion_basis_row = _v13_row_contains(
        "Số trẻ làm căn cứ",
        "hoàn thành",
    )

    completion_count_row = _v13_row_contains(
        "Số trẻ hoàn thành",
        "Chương trình GDMN theo độ tuổi",
    )

    if completion_count_row == completion_basis_row:
        completion_count_row = None

    completion_ratio_row = _v13_row_contains(
        "Tỉ lệ hoàn thành chương trình GDMN"
    )

    # ----------------------------------------------------------
    # B. ĐIỀN HỌC 2 BUỔI/NGÀY
    # ----------------------------------------------------------
    two_sessions = metrics.get(
        "two_sessions",
        {},
    )

    if two_sessions_row:
        for age, col in age_cols.items():
            ws[
                f"{col}{two_sessions_row}"
            ] = int(
                two_sessions.get(
                    age,
                    0,
                )
                or 0
            )

        total_col_letter = "M"

        ws[
            f"{total_col_letter}{two_sessions_row}"
        ] = int(
            sum(
                int(
                    two_sessions.get(
                        age,
                        0,
                    )
                    or 0
                )
                for age in range(0, 6)
            )
        )

    # ----------------------------------------------------------
    # C. TỶ LỆ BẢNG CHÍNH
    # ----------------------------------------------------------
    total_col_letter = "M"

    ratio_columns = list(
        age_cols.values()
    ) + [total_col_letter]

    if (
        must_mobilize_row
        and attending_row
        and mobilization_ratio_row
    ):
        for col in ratio_columns:
            value = _v13_ratio_decimal(
                _v13_cell(
                    attending_row,
                    col,
                ),
                _v13_cell(
                    must_mobilize_row,
                    col,
                ),
            )

            ws[
                f"{col}{mobilization_ratio_row}"
            ] = (
                value
                if value is not None
                else ""
            )

    if (
        two_sessions_row
        and attending_row
        and two_sessions_ratio_row
    ):
        for col in ratio_columns:
            value = _v13_pct100(
                _v13_cell(
                    two_sessions_row,
                    col,
                ),
                _v13_cell(
                    attending_row,
                    col,
                ),
            )

            ws[
                f"{col}{two_sessions_ratio_row}"
            ] = (
                value
                if value is not None
                else ""
            )

    if (
        completion_basis_row
        and completion_count_row
        and completion_ratio_row
    ):
        for col in ratio_columns:
            value = _v13_pct100(
                _v13_cell(
                    completion_count_row,
                    col,
                ),
                _v13_cell(
                    completion_basis_row,
                    col,
                ),
            )

            ws[
                f"{col}{completion_ratio_row}"
            ] = (
                value
                if value is not None
                else ""
            )

    # ----------------------------------------------------------
    # D. BẢNG TIÊU CHÍ PHÍA DƯỚI
    # ----------------------------------------------------------
    criteria_header_row = _v13_row_contains(
        "Tiêu chí",
        "Số lượng",
        "Tỉ lệ",
        start_row=25,
    )

    quantity_col = _v13_header_column(
        criteria_header_row,
        "Số lượng",
    )

    percentage_col = _v13_header_column(
        criteria_header_row,
        "Tỉ lệ",
    )

    def _v13_write_criterion(
        row_no,
        quantity,
        percentage,
    ):
        if (
            not row_no
            or not quantity_col
            or not percentage_col
        ):
            return

        quantity_value = quantity

        if isinstance(
            quantity,
            (int, float),
        ):
            q_float = float(quantity)

            if q_float.is_integer():
                quantity_value = int(
                    q_float
                )

        ws.cell(
            row=row_no,
            column=quantity_col,
        ).value = quantity_value

        ws.cell(
            row=row_no,
            column=percentage_col,
        ).value = (
            percentage
            if percentage is not None
            else ""
        )

    criteria_start = (
        criteria_header_row + 1
        if criteria_header_row
        else 1
    )

    row_5_attending = _v13_row_contains(
        "Trẻ 5 tuổi đến trường",
        start_row=criteria_start,
    )

    row_5_completed = _v13_row_contains(
        "Trẻ 5 tuổi hoàn thành chương trình GDMN",
        start_row=criteria_start,
    )

    row_5_disability = _v13_row_contains(
        "Trẻ 5 tuổi khuyết tật",
        "tiếp cận",
        start_row=criteria_start,
    )

    row_5_two_sessions = _v13_row_contains(
        "Trẻ học 2 buổi/ngày",
        start_row=criteria_start,
    )

    row_34_attending = _v13_row_contains(
        "Trẻ 3, 4 tuổi đến trường",
        start_row=criteria_start,
    )

    row_34_completed = _v13_row_contains(
        "Trẻ 3, 4 tuổi hoàn thành",
        start_row=criteria_start,
    )

    row_34_two_sessions = _v13_row_contains(
        "Trẻ 3, 4 tuổi học 2 buổi/ngày",
        start_row=criteria_start,
    )

    col_age_5 = age_cols.get(5)

    quantity = (
        _v13_number(
            _v13_cell(
                attending_row,
                col_age_5,
            )
        )
        if col_age_5
        else None
    )

    percentage = (
        _v13_pct100(
            quantity,
            _v13_cell(
                total_children_row,
                col_age_5,
            ),
        )
        if col_age_5
        else None
    )

    _v13_write_criterion(
        row_5_attending,
        quantity,
        percentage,
    )

    quantity = (
        _v13_number(
            _v13_cell(
                completion_count_row,
                col_age_5,
            )
        )
        if col_age_5
        else None
    )

    percentage = (
        _v13_pct100(
            quantity,
            _v13_cell(
                completion_basis_row,
                col_age_5,
            ),
        )
        if col_age_5
        else None
    )

    _v13_write_criterion(
        row_5_completed,
        quantity,
        percentage,
    )

    quantity = (
        _v13_number(
            _v13_cell(
                disability_access_row,
                col_age_5,
            )
        )
        if col_age_5
        else None
    )

    percentage = (
        _v13_pct100(
            quantity,
            _v13_cell(
                disability_total_row,
                col_age_5,
            ),
        )
        if col_age_5
        else None
    )

    _v13_write_criterion(
        row_5_disability,
        quantity,
        percentage,
    )

    quantity = (
        _v13_number(
            _v13_cell(
                two_sessions_row,
                col_age_5,
            )
        )
        if col_age_5
        else None
    )

    percentage = (
        _v13_pct100(
            quantity,
            _v13_cell(
                attending_row,
                col_age_5,
            ),
        )
        if col_age_5
        else None
    )

    _v13_write_criterion(
        row_5_two_sessions,
        quantity,
        percentage,
    )

    quantity = _v13_sum_ages(
        attending_row,
        (3, 4),
    )

    percentage = _v13_pct100(
        quantity,
        _v13_sum_ages(
            total_children_row,
            (3, 4),
        ),
    )

    _v13_write_criterion(
        row_34_attending,
        quantity,
        percentage,
    )

    quantity = _v13_sum_ages(
        completion_count_row,
        (3, 4),
    )

    percentage = _v13_pct100(
        quantity,
        _v13_sum_ages(
            completion_basis_row,
            (3, 4),
        ),
    )

    _v13_write_criterion(
        row_34_completed,
        quantity,
        percentage,
    )

    quantity = _v13_sum_ages(
        two_sessions_row,
        (3, 4),
    )

    percentage = _v13_pct100(
        quantity,
        _v13_sum_ages(
            attending_row,
            (3, 4),
        ),
    )

    _v13_write_criterion(
        row_34_two_sessions,
        quantity,
        percentage,
    )

    # Không cần Excel tính lại công thức mới:
    # toàn bộ tỷ lệ V1.3 đã được ghi thành số trực tiếp.
    # === BAO_CAO_MN_MAU_MOI_V1_3_TY_LE_TRUC_TIEP END ===

    # === BAI_13B_11_15_2_4_6_5_POSTPROCESS_BEFORE_SAVE_START ===
    _v246_capable = metrics.get("disabled_capable", {})
    _v246_access = metrics.get("disabled_access_v246", {})
    _v246_age_cols = {0:'F',1:'G',2:'H',3:'I',4:'J',5:'K',6:'L'}
    for _v246_age, _v246_col in _v246_age_cols.items():
        _v246_den = int(_v246_capable.get(_v246_age, 0) or 0)
        _v246_num = int(_v246_access.get(_v246_age, 0) or 0)
        ws[f'{_v246_col}10'] = _v246_den if _v246_den > 0 else None
        ws[f'{_v246_col}11'] = _v246_num if _v246_den > 0 else None
    ws['M10'] = sum(int(_v246_capable.get(a,0) or 0) for a in range(6)) or None
    ws['M11'] = sum(int(_v246_access.get(a,0) or 0) for a in range(6)) if ws['M10'].value else None
    from app.services.mn_report_v246 import apply_formula_contract
    apply_formula_contract(wb)
    # === BAI_13B_11_15_2_4_6_5_POSTPROCESS_BEFORE_SAVE_END ===

    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()

def _ratio(n: int, d: int) -> float | None:
    if not d:
        return None
    return round(float(n) / float(d), 2)


def _percent(n: int, d: int) -> float | None:
    if not d:
        return None
    return round(100.0 * float(n) / float(d), 2)


def _shift_merges_for_insert(ws, idx: int, amount: int) -> None:
    from openpyxl.utils.cell import range_boundaries
    ranges = [str(r) for r in ws.merged_cells.ranges]
    for r in ranges:
        ws.unmerge_cells(r)
    ws.insert_rows(idx, amount)
    for r in ranges:
        min_col, min_row, max_col, max_row = range_boundaries(r)
        if min_row >= idx:
            min_row += amount
            max_row += amount
        elif max_row >= idx:
            max_row += amount
        ws.merge_cells(
            start_row=min_row, start_column=min_col,
            end_row=max_row, end_column=max_col,
        )


def _clone_row_style(ws, src_row: int, dst_row: int, max_col: int = 19) -> None:
    ws.row_dimensions[dst_row].height = ws.row_dimensions[src_row].height
    for col in range(1, max_col + 1):
        src = ws.cell(src_row, col)
        dst = ws.cell(dst_row, col)
        if src.has_style:
            dst._style = copy(src._style)
        if src.number_format:
            dst.number_format = src.number_format
        if src.font:
            dst.font = copy(src.font)
        if src.fill:
            dst.fill = copy(src.fill)
        if src.border:
            dst.border = copy(src.border)
        if src.alignment:
            dst.alignment = copy(src.alignment)
        if src.protection:
            dst.protection = copy(src.protection)


def _merge_pair_A_H(ws, top: int) -> None:
    for col in range(1, 9):
        ws.merge_cells(start_row=top, start_column=col, end_row=top + 1, end_column=col)


def _clear_pair(ws, top: int) -> None:
    for col in range(1, 9):
        ws.cell(top, col).value = None
    for row in (top, top + 1):
        for col in range(9, 20):
            ws.cell(row, col).value = None


def _write_age_metric(ws, row_no: int, label: str, metric: dict[str, Any]) -> None:
    teachers = int(metric.get("teachers", 0) or 0)
    ws.cell(row_no, 9).value = label
    ws.cell(row_no, 10).value = int(metric.get("classes", 0) or 0)
    ws.cell(row_no, 11).value = teachers
    ws.cell(row_no, 12).value = int(metric.get("contract", 0) or 0)
    ws.cell(row_no, 13).value = int(metric.get("policy", 0) or 0)
    ws.cell(row_no, 14).value = _ratio(teachers, int(metric.get("classes", 0) or 0))
    standard = int(metric.get("standard", 0) or 0)
    above = int(metric.get("above", 0) or 0)
    ws.cell(row_no, 15).value = standard
    ws.cell(row_no, 16).value = above
    ws.cell(row_no, 17).value = _percent(standard + above, teachers)
    prof = int(metric.get("professional_pass", 0) or 0)
    ws.cell(row_no, 18).value = prof
    ws.cell(row_no, 19).value = _percent(prof, teachers)


def _write_gv_pair(ws, top: int, stt: int, item: dict[str, Any]) -> None:
    m = item["metric"]
    ws.cell(top, 1).value = stt
    ws.cell(top, 2).value = item["name"]
    ws.cell(top, 3).value = int(m["staff"])
    ws.cell(top, 4).value = int(m["contract_staff"])
    ws.cell(top, 5).value = int(m["managers"])
    ws.cell(top, 6).value = int(m["teachers"])
    ws.cell(top, 7).value = _ratio(int(m["teachers"]), int(m["classes_total"]))
    ws.cell(top, 8).value = int(m["employees"])
    _write_age_metric(ws, top, "3-4 tuổi", m["age"]["3_4"])
    _write_age_metric(ws, top + 1, "5 tuổi", m["age"]["5"])


def _fill_gv_workbook(scope: dict[str, Any], items: list[dict[str, Any]]) -> bytes:
    from openpyxl import load_workbook

    wb = load_workbook(GV_TEMPLATE_PATH)
    ws = wb["MG"]
    year_code = str((scope.get("selected_year") or {}).get("code") or "")
    commune_name = str((scope.get("selected_commune") or {}).get("name") or scope.get("scope_label") or "Toàn tỉnh")
    ws["A1"] = f"Xã: {commune_name}"
    ws["A2"] = "Tỉnh: Nghệ An"
    ws["C2"] = f"Thời điểm: tháng {date.today().month:02d} năm {(_report_year_start(year_code))}"

    schools = [item for item in items if not item["independent"]]
    independents = [item for item in items if item["independent"]]

    # Mở rộng phần TRƯỜNG MẦM NON tại dòng 16 trước khi phần cơ sở độc lập bắt đầu.
    extra_school_pairs = max(0, len(schools) - 2)
    if extra_school_pairs:
        amount = extra_school_pairs * 2
        _shift_merges_for_insert(ws, 16, amount)
        for index in range(extra_school_pairs):
            top = 16 + index * 2
            _clone_row_style(ws, 12, top)
            _clone_row_style(ws, 13, top + 1)
            _merge_pair_A_H(ws, top)
    school_ellipsis_row = 16 + extra_school_pairs * 2
    ws.cell(school_ellipsis_row, 2).value = None

    independent_header = 17 + extra_school_pairs * 2
    independent_first_top = independent_header + 1
    independent_ellipsis = independent_header + 5

    extra_ind_pairs = max(0, len(independents) - 2)
    if extra_ind_pairs:
        amount = extra_ind_pairs * 2
        _shift_merges_for_insert(ws, independent_ellipsis, amount)
        for index in range(extra_ind_pairs):
            top = independent_ellipsis + index * 2
            _clone_row_style(ws, independent_first_top, top)
            _clone_row_style(ws, independent_first_top + 1, top + 1)
            _merge_pair_A_H(ws, top)
    independent_ellipsis = independent_header + 5 + extra_ind_pairs * 2
    ws.cell(independent_ellipsis, 2).value = None

    # Tổng số theo phạm vi.
    total = _aggregate_gv(items)
    ws["C8"] = int(total["staff"])
    ws["D8"] = int(total["contract_staff"])
    ws["E8"] = int(total["managers"])
    ws["F8"] = int(total["teachers"])
    ws["G8"] = _ratio(int(total["teachers"]), int(total["classes_total"]))
    ws["H8"] = int(total["employees"])
    _write_age_metric(ws, 9, "3-4 tuổi", total["age"]["3_4"])
    _write_age_metric(ws, 10, "5 tuổi", total["age"]["5"])

    # Có tối thiểu hai cặp mẫu trong mỗi nhóm; xóa dữ liệu mẫu trước rồi ghi dữ liệu thật.
    school_pair_tops = [12 + i * 2 for i in range(max(2, len(schools)))]
    for top in school_pair_tops:
        _clear_pair(ws, top)
    for idx, item in enumerate(schools, 1):
        _write_gv_pair(ws, school_pair_tops[idx - 1], idx, item)

    independent_pair_tops = [independent_first_top + i * 2 for i in range(max(2, len(independents)))]
    for top in independent_pair_tops:
        _clear_pair(ws, top)
    for idx, item in enumerate(independents, 1):
        _write_gv_pair(ws, independent_pair_tops[idx - 1], idx, item)

    # Vùng in kết thúc sau phần chữ ký đã được dịch xuống.
    signature_last = 26 + extra_school_pairs * 2 + extra_ind_pairs * 2
    ws.print_area = f"A1:S{signature_last}"

    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def _page(
    report_kind: str,
    request: Request,
    school_year_id: int | None,
    commune_id: int | None,
    school_id: int | None,
    db: Session,
):
    scope = _build_scope(db, request, school_year_id, commune_id, school_id)
    if scope is None:
        return _forbidden()
    if report_kind == "te":
        rows = _query_te_people(db, scope)
        year_code = str((scope.get("selected_year") or {}).get("code") or "")
        context = _te_context(scope, rows, _te_metrics(rows, year_code))
    else:
        rows, summaries = _query_gv_rows(db, scope)
        items = _gv_school_metrics(rows, summaries)
        context = _gv_context(scope, items)
    context["nguoi_dung"] = scope["user"]
    return templates.TemplateResponse(
        request=request,
        name="reports/mn_official_report.html",
        context=context,
    )


@router.get("/bao-cao/mn-01-te", response_class=HTMLResponse)
def mn01te_page(
    request: Request,
    school_year_id: str | None = None,
    commune_id: str | None = None,
    school_id: str | None = None,
    db: Session = Depends(get_db),
):
    params = [("sheet_code", "mn-01-te")]
    if school_year_id not in (None, ""):
        params.append(("school_year_id", str(school_year_id)))
    if commune_id not in (None, ""):
        params.append(("commune_id", str(commune_id)))
    if school_id not in (None, ""):
        params.append(("school_id", str(school_id)))

    return RedirectResponse(
        url="/bao-cao/pcgdmn-mau-2025?" + urlencode(params),
        status_code=303,
    )


@router.get("/bao-cao/mn-01-gv-bgd", response_class=HTMLResponse)
def mn01gv_bgd_page(
    request: Request,
    school_year_id: str | None = None,
    commune_id: str | None = None,
    school_id: str | None = None,
    db: Session = Depends(get_db),
):
    params = [("sheet_code", "mn-01-gv")]
    if school_year_id not in (None, ""):
        params.append(("school_year_id", str(school_year_id)))
    if commune_id not in (None, ""):
        params.append(("commune_id", str(commune_id)))
    if school_id not in (None, ""):
        params.append(("school_id", str(school_id)))

    return RedirectResponse(
        url="/bao-cao/pcgdmn-mau-2025?" + urlencode(params),
        status_code=303,
    )


@router.get("/bao-cao/mn-01-te/xuat-excel")
def mn01te_export(
    request: Request,
    school_year_id: str | None = None,
    commune_id: str | None = None,
    school_id: str | None = None,
    db: Session = Depends(get_db),
):
    params = []
    if school_year_id not in (None, ""):
        params.append(("school_year_id", str(school_year_id)))
    if commune_id not in (None, ""):
        params.append(("commune_id", str(commune_id)))
    if school_id not in (None, ""):
        params.append(("school_id", str(school_id)))

    query = urlencode(params)
    return RedirectResponse(
        url=(
            "/bao-cao/pcgdmn-mau-2025/xuat-bieu/mn-01-te"
            + (f"?{query}" if query else "")
        ),
        status_code=303,
    )


@router.get("/bao-cao/mn-01-gv-bgd/xuat-excel")
def mn01gv_bgd_export(
    request: Request,
    school_year_id: str | None = None,
    commune_id: str | None = None,
    school_id: str | None = None,
    db: Session = Depends(get_db),
):
    params = []
    if school_year_id not in (None, ""):
        params.append(("school_year_id", str(school_year_id)))
    if commune_id not in (None, ""):
        params.append(("commune_id", str(commune_id)))
    if school_id not in (None, ""):
        params.append(("school_id", str(school_id)))

    query = urlencode(params)
    return RedirectResponse(
        url=(
            "/bao-cao/pcgdmn-mau-2025/xuat-bieu/mn-01-gv"
            + (f"?{query}" if query else "")
        ),
        status_code=303,
    )


def install_mn_official_report_redirects(app) -> None:
    """
    V2.4.3.4:
    Giữ tương thích link/mã báo cáo Mầm non cũ, nhưng toàn bộ
    5 mã report_type cũ được đưa về cùng pipeline master 7 sheet.
    """
    if getattr(app.state, "_mn_official_reports_v1_redirect", False):
        return
    app.state._mn_official_reports_v1_redirect = True

    @app.middleware("http")
    async def _mn_report_redirect(request: Request, call_next):
        if (
            request.method in {"GET", "HEAD"}
            and request.url.path.startswith("/bao-cao")
        ):
            old_code = request.query_params.get("report_type")
            sheet_code = OLD_TO_NEW.get(str(old_code or ""))
            if sheet_code:
                params = [
                    (key, value)
                    for key, value in request.query_params.multi_items()
                    if key != "report_type"
                ]

                is_export = "xuat" in request.url.path.lower()
                if is_export:
                    target = (
                        "/bao-cao/pcgdmn-mau-2025/xuat-bieu/"
                        + sheet_code
                    )
                else:
                    target = "/bao-cao/pcgdmn-mau-2025"
                    params.append(("sheet_code", sheet_code))

                query = urlencode(params)
                return RedirectResponse(
                    url=target + (f"?{query}" if query else ""),
                    status_code=303,
                )

        return await call_next(request)

# === BAO_CAO_MN_MAU_MOI_V1_1_EMPTY_QUERY_FIX ===
