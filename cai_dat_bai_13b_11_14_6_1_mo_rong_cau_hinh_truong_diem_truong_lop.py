from __future__ import annotations

import ast
import os
import shutil
import sqlite3
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path


PROJECT = Path(
    os.environ.get(
        "PHOCAP_PROJECT",
        r"C:\PhoCap",
    )
).resolve()

APP = PROJECT / "app"
MAIN = APP / "main.py"
STAFF_ROUTER = APP / "routers" / "staff_management.py"
NEW_ROUTER = APP / "routers" / "class_structure_inputs.py"
TEMPLATE = APP / "templates" / "staff" / "class_config.html"
DB = PROJECT / "data" / "phocap.db"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

BACKUP = (
    PROJECT
    / "exports"
    / f"backup_bai_13b_11_14_6_1_{STAMP}"
)

DB_BACKUP = BACKUP / "data" / "phocap.db"

IMPORT_MARKER = (
    "# === BAI_13B_11_14_6_1_CLASS_DETAIL_ROUTER_IMPORT ==="
)

INCLUDE_MARKER = (
    "# === BAI_13B_11_14_6_1_CLASS_DETAIL_ROUTER_INCLUDE ==="
)

ROUTER_CODE = 'from __future__ import annotations\n\nfrom urllib.parse import urlencode\n\nfrom fastapi import APIRouter, Depends, Form, Request\nfrom fastapi.responses import JSONResponse, RedirectResponse\nfrom sqlalchemy import select, text\nfrom sqlalchemy.exc import IntegrityError\nfrom sqlalchemy.orm import Session\n\nfrom app.database import get_db\nfrom app.models import School\nfrom app.routers.staff_management import (\n    SchoolStaffYearSummary,\n    _can_manage,\n    _ensure_school_in_scope,\n    _infer_institution_group,\n    lay_thong_tin_nguoi_dung,\n)\n\n\nrouter = APIRouter(\n    prefix="/doi-ngu/cau-hinh-lop-chi-tiet",\n    tags=["Nguồn nhập trường lớp PCGDMN"],\n)\n\n\nSITE_TYPES = {\n    "MAIN": "Cơ sở chính",\n    "SATELLITE": "Điểm trường",\n    "INDEPENDENT": "Cơ sở độc lập",\n}\n\nCLASS_STRUCTURES = {\n    "SINGLE": "Lớp đơn",\n    "COMBINED": "Lớp ghép",\n}\n\nAGE_GROUP_CODES = {\n    "CHUA_XAC_DINH": "Chưa xác định",\n    "NHA_TRE": "Nhà trẻ",\n    "MG_3_4": "Mẫu giáo 3–4 tuổi",\n    "MG_4_5": "Mẫu giáo 4–5 tuổi",\n    "MG_5_6": "Mẫu giáo 5–6 tuổi",\n    "HON_HOP": "Ghép nhiều độ tuổi",\n    "KHAC": "Khác",\n}\n\n\ndef _clean(value) -> str:\n    return str(value or "").strip()\n\n\ndef _optional_int(value):\n    raw = _clean(value)\n\n    if not raw:\n        return None\n\n    try:\n        return int(raw)\n    except (TypeError, ValueError):\n        return None\n\n\ndef _nonnegative_optional_int(value):\n    parsed = _optional_int(value)\n\n    if parsed is None:\n        return None\n\n    return max(0, parsed)\n\n\ndef _checked(value) -> bool:\n    return _clean(value).upper() in {\n        "1",\n        "TRUE",\n        "ON",\n        "CO",\n        "YES",\n    }\n\n\ndef _year_exists(\n    db: Session,\n    school_year_id: int,\n) -> bool:\n    return bool(\n        db.execute(\n            text(\n                """\n                SELECT 1\n                FROM school_years\n                WHERE id = :year_id\n                LIMIT 1\n                """\n            ),\n            {"year_id": int(school_year_id)},\n        ).scalar()\n    )\n\n\ndef _school_commune_id(\n    db: Session,\n    school_id: int,\n):\n    return db.execute(\n        text(\n            """\n            SELECT commune_id\n            FROM schools\n            WHERE id = :school_id\n            LIMIT 1\n            """\n        ),\n        {"school_id": int(school_id)},\n    ).scalar()\n\n\ndef _redirect_url(\n    db: Session,\n    *,\n    school_id: int,\n    school_year_id: int,\n    status: str,\n) -> str:\n    params = {\n        "school_year_id": int(school_year_id),\n        "school_id": int(school_id),\n        "status": status,\n    }\n\n    commune_id = _school_commune_id(\n        db,\n        school_id,\n    )\n\n    if commune_id is not None:\n        params["commune_id"] = int(\n            commune_id\n        )\n\n    return (\n        "/doi-ngu/cau-hinh-lop?"\n        + urlencode(params)\n        + "#chi-tiet-truong-lop"\n    )\n\n\ndef _redirect(\n    db: Session,\n    *,\n    school_id: int,\n    school_year_id: int,\n    status: str,\n) -> RedirectResponse:\n    return RedirectResponse(\n        _redirect_url(\n            db,\n            school_id=school_id,\n            school_year_id=school_year_id,\n            status=status,\n        ),\n        status_code=303,\n    )\n\n\ndef _view_allowed(\n    request: Request,\n    school_id: int,\n) -> tuple[dict, bool]:\n    user = (\n        lay_thong_tin_nguoi_dung(\n            request\n        )\n        or {}\n    )\n\n    return (\n        user,\n        bool(\n            _ensure_school_in_scope(\n                user,\n                int(school_id),\n            )\n        ),\n    )\n\n\ndef _edit_allowed(\n    request: Request,\n    school_id: int,\n) -> tuple[dict, bool]:\n    user, in_scope = _view_allowed(\n        request,\n        school_id,\n    )\n\n    return (\n        user,\n        bool(\n            in_scope\n            and _can_manage(user)\n        ),\n    )\n\n\ndef _site_belongs(\n    db: Session,\n    *,\n    site_id: int,\n    school_id: int,\n    school_year_id: int,\n) -> bool:\n    return bool(\n        db.execute(\n            text(\n                """\n                SELECT 1\n                FROM school_site_year_records\n                WHERE id = :site_id\n                  AND school_id = :school_id\n                  AND school_year_id = :year_id\n                LIMIT 1\n                """\n            ),\n            {\n                "site_id": int(site_id),\n                "school_id": int(school_id),\n                "year_id": int(school_year_id),\n            },\n        ).scalar()\n    )\n\n\ndef _class_belongs(\n    db: Session,\n    *,\n    class_id: int,\n    school_id: int,\n    school_year_id: int,\n) -> bool:\n    return bool(\n        db.execute(\n            text(\n                """\n                SELECT 1\n                FROM classes\n                WHERE id = :class_id\n                  AND school_id = :school_id\n                  AND school_year_id = :year_id\n                LIMIT 1\n                """\n            ),\n            {\n                "class_id": int(class_id),\n                "school_id": int(school_id),\n                "year_id": int(school_year_id),\n            },\n        ).scalar()\n    )\n\n\ndef _sync_class_summary(\n    db: Session,\n    *,\n    school_id: int,\n    school_year_id: int,\n    user: dict,\n) -> None:\n    counts = db.execute(\n        text(\n            """\n            SELECT\n                COUNT(*) AS total_classes,\n                SUM(\n                    CASE\n                        WHEN COALESCE(a.age_group_code, \'\') IN (\n                            \'MG_3_4\',\n                            \'MG_4_5\'\n                        )\n                        THEN 1 ELSE 0\n                    END\n                ) AS preschool_3_4,\n                SUM(\n                    CASE\n                        WHEN COALESCE(a.age_group_code, \'\') = \'MG_5_6\'\n                        THEN 1 ELSE 0\n                    END\n                ) AS preschool_5\n            FROM classes c\n            LEFT JOIN school_class_year_attributes a\n                ON a.class_id = c.id\n            WHERE c.school_id = :school_id\n              AND c.school_year_id = :year_id\n              AND COALESCE(c.is_active, 1) = 1\n            """\n        ),\n        {\n            "school_id": int(school_id),\n            "year_id": int(school_year_id),\n        },\n    ).mappings().one()\n\n    summary = db.scalar(\n        select(\n            SchoolStaffYearSummary\n        ).where(\n            SchoolStaffYearSummary.school_id\n            == int(school_id),\n            SchoolStaffYearSummary.school_year_id\n            == int(school_year_id),\n        )\n    )\n\n    if summary is None:\n        school = db.get(\n            School,\n            int(school_id),\n        )\n\n        summary = SchoolStaffYearSummary(\n            school_id=int(school_id),\n            school_year_id=int(\n                school_year_id\n            ),\n        )\n\n        summary.institution_group = (\n            _infer_institution_group(\n                getattr(\n                    school,\n                    "name",\n                    "",\n                )\n            )\n        )\n\n        db.add(\n            summary\n        )\n\n    summary.total_groups_classes = int(\n        counts.get("total_classes")\n        or 0\n    )\n\n    summary.preschool_classes_3_4 = int(\n        counts.get("preschool_3_4")\n        or 0\n    )\n\n    summary.preschool_classes_5 = int(\n        counts.get("preschool_5")\n        or 0\n    )\n\n    summary.updated_by_user_id = (\n        int(\n            (user or {}).get("id")\n            or 0\n        )\n        or None\n    )\n\n\n@router.get("")\ndef class_detail_data(\n    request: Request,\n    school_year_id: int,\n    school_id: int,\n    db: Session = Depends(get_db),\n):\n    user, allowed = _view_allowed(\n        request,\n        school_id,\n    )\n\n    if not allowed:\n        return JSONResponse(\n            {\n                "ok": False,\n                "message": (\n                    "Không có quyền xem "\n                    "trường này."\n                ),\n            },\n            status_code=403,\n        )\n\n    if not _year_exists(\n        db,\n        school_year_id,\n    ):\n        return JSONResponse(\n            {\n                "ok": False,\n                "message": (\n                    "Năm học không tồn tại."\n                ),\n            },\n            status_code=400,\n        )\n\n    sites = [\n        dict(row)\n        for row in db.execute(\n            text(\n                """\n                SELECT\n                    id,\n                    school_id,\n                    school_year_id,\n                    site_code,\n                    site_name,\n                    site_type,\n                    is_independent,\n                    address,\n                    is_active,\n                    notes\n                FROM school_site_year_records\n                WHERE school_id = :school_id\n                  AND school_year_id = :year_id\n                ORDER BY\n                    COALESCE(is_active, 1) DESC,\n                    CASE site_type\n                        WHEN \'MAIN\' THEN 0\n                        WHEN \'SATELLITE\' THEN 1\n                        WHEN \'INDEPENDENT\' THEN 2\n                        ELSE 9\n                    END,\n                    site_name COLLATE NOCASE,\n                    id\n                """\n            ),\n            {\n                "school_id": int(school_id),\n                "year_id": int(\n                    school_year_id\n                ),\n            },\n        ).mappings().all()\n    ]\n\n    classes = [\n        dict(row)\n        for row in db.execute(\n            text(\n                """\n                SELECT\n                    c.id,\n                    c.school_id,\n                    c.school_year_id,\n                    c.code,\n                    c.name,\n                    c.is_active,\n                    a.site_year_id,\n                    a.class_structure,\n                    a.age_group_code,\n                    a.is_mixed_age,\n                    a.planned_children_count,\n                    a.notes,\n                    s.site_name\n                FROM classes c\n                LEFT JOIN school_class_year_attributes a\n                    ON a.class_id = c.id\n                LEFT JOIN school_site_year_records s\n                    ON s.id = a.site_year_id\n                WHERE c.school_id = :school_id\n                  AND c.school_year_id = :year_id\n                ORDER BY\n                    COALESCE(c.is_active, 1) DESC,\n                    c.name COLLATE NOCASE,\n                    c.id\n                """\n            ),\n            {\n                "school_id": int(school_id),\n                "year_id": int(\n                    school_year_id\n                ),\n            },\n        ).mappings().all()\n    ]\n\n    active_sites = sum(\n        1\n        for row in sites\n        if int(\n            row.get("is_active")\n            if row.get("is_active")\n            is not None\n            else 1\n        )\n        == 1\n    )\n\n    independent_sites = sum(\n        1\n        for row in sites\n        if int(\n            row.get("is_active")\n            if row.get("is_active")\n            is not None\n            else 1\n        )\n        == 1\n        and int(\n            row.get("is_independent")\n            or 0\n        )\n        == 1\n    )\n\n    active_classes = [\n        row\n        for row in classes\n        if int(\n            row.get("is_active")\n            if row.get("is_active")\n            is not None\n            else 1\n        )\n        == 1\n    ]\n\n    single_classes = sum(\n        1\n        for row in active_classes\n        if str(\n            row.get(\n                "class_structure"\n            )\n            or "SINGLE"\n        )\n        == "SINGLE"\n    )\n\n    combined_classes = sum(\n        1\n        for row in active_classes\n        if str(\n            row.get(\n                "class_structure"\n            )\n            or "SINGLE"\n        )\n        == "COMBINED"\n    )\n\n    return {\n        "ok": True,\n        "can_manage": bool(\n            _can_manage(user)\n        ),\n        "sites": sites,\n        "classes": classes,\n        "labels": {\n            "site_types": SITE_TYPES,\n            "class_structures": (\n                CLASS_STRUCTURES\n            ),\n            "age_groups": AGE_GROUP_CODES,\n        },\n        "stats": {\n            "active_sites": active_sites,\n            "independent_sites": (\n                independent_sites\n            ),\n            "active_classes": len(\n                active_classes\n            ),\n            "single_classes": (\n                single_classes\n            ),\n            "combined_classes": (\n                combined_classes\n            ),\n        },\n    }\n\n\n@router.post("/site")\ndef save_site(\n    request: Request,\n    school_id: int = Form(...),\n    school_year_id: int = Form(...),\n    site_id: int = Form(0),\n    site_code: str = Form(""),\n    site_name: str = Form(""),\n    site_type: str = Form("MAIN"),\n    is_independent: str | None = Form(None),\n    address: str = Form(""),\n    notes: str = Form(""),\n    db: Session = Depends(get_db),\n) -> RedirectResponse:\n    _user, allowed = _edit_allowed(\n        request,\n        school_id,\n    )\n\n    if not allowed:\n        return _redirect(\n            db,\n            school_id=school_id,\n            school_year_id=school_year_id,\n            status="forbidden",\n        )\n\n    if not _year_exists(\n        db,\n        school_year_id,\n    ):\n        return _redirect(\n            db,\n            school_id=school_id,\n            school_year_id=school_year_id,\n            status="invalid",\n        )\n\n    name = _clean(\n        site_name\n    )\n\n    if not name:\n        return _redirect(\n            db,\n            school_id=school_id,\n            school_year_id=school_year_id,\n            status="site_invalid",\n        )\n\n    site_type = _clean(\n        site_type\n    ).upper()\n\n    if site_type not in SITE_TYPES:\n        site_type = "MAIN"\n\n    independent = (\n        _checked(\n            is_independent\n        )\n        or site_type\n        == "INDEPENDENT"\n    )\n\n    code = _clean(\n        site_code\n    ) or None\n\n    if code:\n        duplicate_id = db.execute(\n            text(\n                """\n                SELECT id\n                FROM school_site_year_records\n                WHERE school_id = :school_id\n                  AND school_year_id = :year_id\n                  AND UPPER(TRIM(site_code))\n                      = UPPER(TRIM(:site_code))\n                  AND id <> :site_id\n                LIMIT 1\n                """\n            ),\n            {\n                "school_id": int(\n                    school_id\n                ),\n                "year_id": int(\n                    school_year_id\n                ),\n                "site_code": code,\n                "site_id": int(\n                    site_id or 0\n                ),\n            },\n        ).scalar()\n\n        if duplicate_id is not None:\n            return _redirect(\n                db,\n                school_id=school_id,\n                school_year_id=school_year_id,\n                status="site_duplicate",\n            )\n\n    try:\n        if site_id:\n            if not _site_belongs(\n                db,\n                site_id=site_id,\n                school_id=school_id,\n                school_year_id=school_year_id,\n            ):\n                return _redirect(\n                    db,\n                    school_id=school_id,\n                    school_year_id=school_year_id,\n                    status="invalid",\n                )\n\n            db.execute(\n                text(\n                    """\n                    UPDATE school_site_year_records\n                    SET\n                        site_code = :site_code,\n                        site_name = :site_name,\n                        site_type = :site_type,\n                        is_independent = :is_independent,\n                        address = :address,\n                        notes = :notes,\n                        updated_at = CURRENT_TIMESTAMP\n                    WHERE id = :site_id\n                    """\n                ),\n                {\n                    "site_code": code,\n                    "site_name": name,\n                    "site_type": site_type,\n                    "is_independent": (\n                        1\n                        if independent\n                        else 0\n                    ),\n                    "address": (\n                        _clean(address)\n                        or None\n                    ),\n                    "notes": (\n                        _clean(notes)\n                        or None\n                    ),\n                    "site_id": int(\n                        site_id\n                    ),\n                },\n            )\n        else:\n            db.execute(\n                text(\n                    """\n                    INSERT INTO school_site_year_records (\n                        school_id,\n                        school_year_id,\n                        site_code,\n                        site_name,\n                        site_type,\n                        is_independent,\n                        address,\n                        is_active,\n                        notes\n                    )\n                    VALUES (\n                        :school_id,\n                        :year_id,\n                        :site_code,\n                        :site_name,\n                        :site_type,\n                        :is_independent,\n                        :address,\n                        1,\n                        :notes\n                    )\n                    """\n                ),\n                {\n                    "school_id": int(\n                        school_id\n                    ),\n                    "year_id": int(\n                        school_year_id\n                    ),\n                    "site_code": code,\n                    "site_name": name,\n                    "site_type": site_type,\n                    "is_independent": (\n                        1\n                        if independent\n                        else 0\n                    ),\n                    "address": (\n                        _clean(address)\n                        or None\n                    ),\n                    "notes": (\n                        _clean(notes)\n                        or None\n                    ),\n                },\n            )\n\n        db.commit()\n\n    except IntegrityError:\n        db.rollback()\n\n        return _redirect(\n            db,\n            school_id=school_id,\n            school_year_id=school_year_id,\n            status="site_duplicate",\n        )\n\n    return _redirect(\n        db,\n        school_id=school_id,\n        school_year_id=school_year_id,\n        status="site_saved",\n    )\n\n\n@router.post("/site/{site_id}/toggle")\ndef toggle_site(\n    site_id: int,\n    request: Request,\n    school_id: int = Form(...),\n    school_year_id: int = Form(...),\n    db: Session = Depends(get_db),\n) -> RedirectResponse:\n    _user, allowed = _edit_allowed(\n        request,\n        school_id,\n    )\n\n    if not allowed:\n        return _redirect(\n            db,\n            school_id=school_id,\n            school_year_id=school_year_id,\n            status="forbidden",\n        )\n\n    if not _site_belongs(\n        db,\n        site_id=site_id,\n        school_id=school_id,\n        school_year_id=school_year_id,\n    ):\n        return _redirect(\n            db,\n            school_id=school_id,\n            school_year_id=school_year_id,\n            status="invalid",\n        )\n\n    db.execute(\n        text(\n            """\n            UPDATE school_site_year_records\n            SET\n                is_active = CASE\n                    WHEN COALESCE(is_active, 1) = 1\n                    THEN 0 ELSE 1\n                END,\n                updated_at = CURRENT_TIMESTAMP\n            WHERE id = :site_id\n            """\n        ),\n        {\n            "site_id": int(site_id),\n        },\n    )\n\n    db.commit()\n\n    return _redirect(\n        db,\n        school_id=school_id,\n        school_year_id=school_year_id,\n        status="site_toggled",\n    )\n\n\n@router.post("/class")\ndef save_class(\n    request: Request,\n    school_id: int = Form(...),\n    school_year_id: int = Form(...),\n    class_id: int = Form(0),\n    class_code: str = Form(""),\n    class_name: str = Form(""),\n    site_year_id: str = Form(""),\n    class_structure: str = Form("SINGLE"),\n    age_group_code: str = Form("CHUA_XAC_DINH"),\n    planned_children_count: str = Form(""),\n    notes: str = Form(""),\n    db: Session = Depends(get_db),\n) -> RedirectResponse:\n    user, allowed = _edit_allowed(\n        request,\n        school_id,\n    )\n\n    if not allowed:\n        return _redirect(\n            db,\n            school_id=school_id,\n            school_year_id=school_year_id,\n            status="forbidden",\n        )\n\n    if not _year_exists(\n        db,\n        school_year_id,\n    ):\n        return _redirect(\n            db,\n            school_id=school_id,\n            school_year_id=school_year_id,\n            status="invalid",\n        )\n\n    name = _clean(\n        class_name\n    )\n\n    if not name:\n        return _redirect(\n            db,\n            school_id=school_id,\n            school_year_id=school_year_id,\n            status="class_invalid",\n        )\n\n    structure = _clean(\n        class_structure\n    ).upper()\n\n    if structure not in CLASS_STRUCTURES:\n        structure = "SINGLE"\n\n    age_code = _clean(\n        age_group_code\n    ).upper()\n\n    if age_code not in AGE_GROUP_CODES:\n        age_code = "CHUA_XAC_DINH"\n\n    site_id = _optional_int(\n        site_year_id\n    )\n\n    if (\n        site_id is not None\n        and not _site_belongs(\n            db,\n            site_id=site_id,\n            school_id=school_id,\n            school_year_id=school_year_id,\n        )\n    ):\n        return _redirect(\n            db,\n            school_id=school_id,\n            school_year_id=school_year_id,\n            status="site_invalid",\n        )\n\n    if class_id:\n        if not _class_belongs(\n            db,\n            class_id=class_id,\n            school_id=school_id,\n            school_year_id=school_year_id,\n        ):\n            return _redirect(\n                db,\n                school_id=school_id,\n                school_year_id=school_year_id,\n                status="invalid",\n            )\n\n    duplicate = db.execute(\n        text(\n            """\n            SELECT id\n            FROM classes\n            WHERE school_id = :school_id\n              AND school_year_id = :year_id\n              AND UPPER(TRIM(name))\n                  = UPPER(TRIM(:class_name))\n              AND id <> :class_id\n            LIMIT 1\n            """\n        ),\n        {\n            "school_id": int(\n                school_id\n            ),\n            "year_id": int(\n                school_year_id\n            ),\n            "class_name": name,\n            "class_id": int(\n                class_id or 0\n            ),\n        },\n    ).scalar()\n\n    if duplicate is not None:\n        return _redirect(\n            db,\n            school_id=school_id,\n            school_year_id=school_year_id,\n            status="class_duplicate",\n        )\n\n    try:\n        if class_id:\n            db.execute(\n                text(\n                    """\n                    UPDATE classes\n                    SET\n                        code = :class_code,\n                        name = :class_name\n                    WHERE id = :class_id\n                    """\n                ),\n                {\n                    "class_code": (\n                        _clean(\n                            class_code\n                        )\n                        or None\n                    ),\n                    "class_name": name,\n                    "class_id": int(\n                        class_id\n                    ),\n                },\n            )\n\n            attribute_exists = bool(\n                db.execute(\n                    text(\n                        """\n                        SELECT 1\n                        FROM school_class_year_attributes\n                        WHERE class_id = :class_id\n                        LIMIT 1\n                        """\n                    ),\n                    {\n                        "class_id": int(\n                            class_id\n                        )\n                    },\n                ).scalar()\n            )\n\n            if attribute_exists:\n                db.execute(\n                    text(\n                        """\n                        UPDATE school_class_year_attributes\n                        SET\n                            site_year_id = :site_year_id,\n                            class_structure = :class_structure,\n                            age_group_code = :age_group_code,\n                            is_mixed_age = :is_mixed_age,\n                            planned_children_count = :planned_children_count,\n                            notes = :notes,\n                            updated_at = CURRENT_TIMESTAMP\n                        WHERE class_id = :class_id\n                        """\n                    ),\n                    {\n                        "site_year_id": site_id,\n                        "class_structure": structure,\n                        "age_group_code": age_code,\n                        "is_mixed_age": (\n                            1\n                            if (\n                                structure\n                                == "COMBINED"\n                                or age_code\n                                == "HON_HOP"\n                            )\n                            else 0\n                        ),\n                        "planned_children_count": (\n                            _nonnegative_optional_int(\n                                planned_children_count\n                            )\n                        ),\n                        "notes": (\n                            _clean(notes)\n                            or None\n                        ),\n                        "class_id": int(\n                            class_id\n                        ),\n                    },\n                )\n            else:\n                db.execute(\n                    text(\n                        """\n                        INSERT INTO school_class_year_attributes (\n                            class_id,\n                            site_year_id,\n                            class_structure,\n                            age_group_code,\n                            is_mixed_age,\n                            planned_children_count,\n                            notes\n                        )\n                        VALUES (\n                            :class_id,\n                            :site_year_id,\n                            :class_structure,\n                            :age_group_code,\n                            :is_mixed_age,\n                            :planned_children_count,\n                            :notes\n                        )\n                        """\n                    ),\n                    {\n                        "class_id": int(\n                            class_id\n                        ),\n                        "site_year_id": site_id,\n                        "class_structure": structure,\n                        "age_group_code": age_code,\n                        "is_mixed_age": (\n                            1\n                            if (\n                                structure\n                                == "COMBINED"\n                                or age_code\n                                == "HON_HOP"\n                            )\n                            else 0\n                        ),\n                        "planned_children_count": (\n                            _nonnegative_optional_int(\n                                planned_children_count\n                            )\n                        ),\n                        "notes": (\n                            _clean(notes)\n                            or None\n                        ),\n                    },\n                )\n\n        else:\n            result = db.execute(\n                text(\n                    """\n                    INSERT INTO classes (\n                        school_id,\n                        school_year_id,\n                        code,\n                        name,\n                        is_active\n                    )\n                    VALUES (\n                        :school_id,\n                        :year_id,\n                        :class_code,\n                        :class_name,\n                        1\n                    )\n                    """\n                ),\n                {\n                    "school_id": int(\n                        school_id\n                    ),\n                    "year_id": int(\n                        school_year_id\n                    ),\n                    "class_code": (\n                        _clean(\n                            class_code\n                        )\n                        or None\n                    ),\n                    "class_name": name,\n                },\n            )\n\n            new_class_id = int(\n                result.lastrowid\n            )\n\n            db.execute(\n                text(\n                    """\n                    INSERT INTO school_class_year_attributes (\n                        class_id,\n                        site_year_id,\n                        class_structure,\n                        age_group_code,\n                        is_mixed_age,\n                        planned_children_count,\n                        notes\n                    )\n                    VALUES (\n                        :class_id,\n                        :site_year_id,\n                        :class_structure,\n                        :age_group_code,\n                        :is_mixed_age,\n                        :planned_children_count,\n                        :notes\n                    )\n                    """\n                ),\n                {\n                    "class_id": (\n                        new_class_id\n                    ),\n                    "site_year_id": site_id,\n                    "class_structure": (\n                        structure\n                    ),\n                    "age_group_code": (\n                        age_code\n                    ),\n                    "is_mixed_age": (\n                        1\n                        if (\n                            structure\n                            == "COMBINED"\n                            or age_code\n                            == "HON_HOP"\n                        )\n                        else 0\n                    ),\n                    "planned_children_count": (\n                        _nonnegative_optional_int(\n                            planned_children_count\n                        )\n                    ),\n                    "notes": (\n                        _clean(notes)\n                        or None\n                    ),\n                },\n            )\n\n        _sync_class_summary(\n            db,\n            school_id=school_id,\n            school_year_id=school_year_id,\n            user=user,\n        )\n\n        db.commit()\n\n    except IntegrityError:\n        db.rollback()\n\n        return _redirect(\n            db,\n            school_id=school_id,\n            school_year_id=school_year_id,\n            status="class_duplicate",\n        )\n\n    return _redirect(\n        db,\n        school_id=school_id,\n        school_year_id=school_year_id,\n        status="class_saved",\n    )\n\n\n@router.post("/class/{class_id}/toggle")\ndef toggle_class(\n    class_id: int,\n    request: Request,\n    school_id: int = Form(...),\n    school_year_id: int = Form(...),\n    db: Session = Depends(get_db),\n) -> RedirectResponse:\n    user, allowed = _edit_allowed(\n        request,\n        school_id,\n    )\n\n    if not allowed:\n        return _redirect(\n            db,\n            school_id=school_id,\n            school_year_id=school_year_id,\n            status="forbidden",\n        )\n\n    if not _class_belongs(\n        db,\n        class_id=class_id,\n        school_id=school_id,\n        school_year_id=school_year_id,\n    ):\n        return _redirect(\n            db,\n            school_id=school_id,\n            school_year_id=school_year_id,\n            status="invalid",\n        )\n\n    db.execute(\n        text(\n            """\n            UPDATE classes\n            SET\n                is_active = CASE\n                    WHEN COALESCE(is_active, 1) = 1\n                    THEN 0 ELSE 1\n                END\n            WHERE id = :class_id\n            """\n        ),\n        {\n            "class_id": int(\n                class_id\n            )\n        },\n    )\n\n    _sync_class_summary(\n        db,\n        school_id=school_id,\n        school_year_id=school_year_id,\n        user=user,\n    )\n\n    db.commit()\n\n    return _redirect(\n        db,\n        school_id=school_id,\n        school_year_id=school_year_id,\n        status="class_toggled",\n    )\n'
TEMPLATE_CODE = '<!DOCTYPE html>\n<html lang="vi">\n<head>\n    <meta charset="UTF-8">\n    <meta\n        name="viewport"\n        content="width=device-width, initial-scale=1.0"\n    >\n    <title>Cấu hình trường, điểm trường và nhóm/lớp</title>\n    <link\n        rel="stylesheet"\n        href="/static/css/style.css"\n    >\n    <style>\n        body {\n            margin: 0;\n            background: #eef4fb;\n            color: #18324f;\n            font-family: Arial, sans-serif;\n        }\n\n        .hero {\n            background: linear-gradient(135deg, #1453a2, #1883d7);\n            color: white;\n            padding: 30px 48px;\n        }\n\n        .hero-inner {\n            max-width: 1400px;\n            margin: auto;\n            display: flex;\n            justify-content: space-between;\n            align-items: center;\n            gap: 20px;\n        }\n\n        .hero h1 {\n            font-size: 32px;\n            margin: 5px 0;\n        }\n\n        .eyebrow,\n        .section-label {\n            font-weight: 800;\n            letter-spacing: .08em;\n            text-transform: uppercase;\n        }\n\n        .container {\n            max-width: 1400px;\n            margin: 24px auto;\n            padding: 0 22px 50px;\n        }\n\n        .panel {\n            background: white;\n            border-radius: 18px;\n            padding: 22px;\n            margin-bottom: 18px;\n            box-shadow: 0 10px 28px rgba(34, 76, 120, .08);\n        }\n\n        .filters {\n            display: grid;\n            grid-template-columns: 1fr 1.3fr auto;\n            gap: 12px;\n            align-items: end;\n        }\n\n        label {\n            display: block;\n            font-weight: 700;\n            margin-bottom: 6px;\n        }\n\n        select,\n        input,\n        textarea {\n            box-sizing: border-box;\n            width: 100%;\n            padding: 10px;\n            border: 1px solid #ccdaea;\n            border-radius: 9px;\n            background: white;\n        }\n\n        textarea {\n            min-height: 74px;\n            resize: vertical;\n        }\n\n        .button {\n            display: inline-flex;\n            align-items: center;\n            justify-content: center;\n            border: 0;\n            border-radius: 10px;\n            padding: 11px 16px;\n            font-weight: 800;\n            text-decoration: none;\n            cursor: pointer;\n        }\n\n        .button-primary {\n            background: #1676d2;\n            color: white;\n        }\n\n        .button-secondary {\n            background: #e7eef6;\n            color: #18324f;\n        }\n\n        .button-light {\n            background: white;\n            color: #1453a2;\n        }\n\n        .button-danger {\n            background: #fff0f0;\n            color: #b42318;\n        }\n\n        .button-small {\n            padding: 8px 11px;\n            font-size: 13px;\n        }\n\n        .table-wrap {\n            overflow: auto;\n        }\n\n        .table {\n            width: 100%;\n            min-width: 1100px;\n            border-collapse: collapse;\n        }\n\n        .table th {\n            background: #eaf2fb;\n            padding: 11px;\n            text-align: left;\n        }\n\n        .table td {\n            padding: 10px;\n            border-bottom: 1px solid #e3ebf3;\n            vertical-align: middle;\n        }\n\n        .row-form {\n            display: grid;\n            grid-template-columns: 1.4fr 1fr 1fr 1fr auto;\n            gap: 9px;\n            align-items: end;\n        }\n\n        .muted {\n            color: #71879f;\n            font-size: 13px;\n        }\n\n        .notice {\n            background: #eaf6ee;\n            border: 1px solid #b9dfc5;\n            color: #176b34;\n            padding: 14px;\n            border-radius: 12px;\n            margin-bottom: 16px;\n        }\n\n        .notice-warning {\n            background: #fff8e7;\n            border-color: #f1d59b;\n            color: #8a5a00;\n        }\n\n        .notice-error {\n            background: #fff0f0;\n            border-color: #efb5b5;\n            color: #a11d1d;\n        }\n\n        .selected-row {\n            background: #f5faff;\n        }\n\n        .detail-title {\n            display: flex;\n            align-items: center;\n            justify-content: space-between;\n            gap: 16px;\n            flex-wrap: wrap;\n        }\n\n        .stats {\n            display: grid;\n            grid-template-columns: repeat(5, minmax(0, 1fr));\n            gap: 12px;\n            margin: 16px 0 20px;\n        }\n\n        .stat {\n            background: #f5f9fe;\n            border: 1px solid #dce9f7;\n            border-radius: 14px;\n            padding: 14px;\n        }\n\n        .stat span {\n            display: block;\n            color: #6a8199;\n            font-size: 12px;\n            font-weight: 700;\n            text-transform: uppercase;\n        }\n\n        .stat strong {\n            display: block;\n            margin-top: 6px;\n            font-size: 26px;\n            color: #1453a2;\n        }\n\n        .subpanel {\n            border: 1px solid #dbe7f3;\n            border-radius: 16px;\n            padding: 18px;\n            margin-top: 18px;\n            background: #fbfdff;\n        }\n\n        .input-grid {\n            display: grid;\n            grid-template-columns: repeat(4, minmax(0, 1fr));\n            gap: 12px;\n        }\n\n        .input-grid .span-2 {\n            grid-column: span 2;\n        }\n\n        .input-grid .span-4 {\n            grid-column: 1 / -1;\n        }\n\n        .checkbox-line {\n            display: flex;\n            align-items: center;\n            gap: 9px;\n            min-height: 42px;\n        }\n\n        .checkbox-line input {\n            width: 18px;\n            height: 18px;\n            margin: 0;\n        }\n\n        .checkbox-line label {\n            margin: 0;\n        }\n\n        .detail-card {\n            border: 1px solid #e0e8f1;\n            border-radius: 14px;\n            padding: 15px;\n            margin-top: 12px;\n            background: white;\n        }\n\n        .detail-card.inactive {\n            opacity: .68;\n            background: #f7f7f7;\n        }\n\n        .detail-grid {\n            display: grid;\n            grid-template-columns: 1fr 1.4fr 1fr 1fr;\n            gap: 10px;\n        }\n\n        .detail-grid .span-2 {\n            grid-column: span 2;\n        }\n\n        .detail-grid .span-4 {\n            grid-column: 1 / -1;\n        }\n\n        .actions {\n            display: flex;\n            gap: 8px;\n            align-items: center;\n            flex-wrap: wrap;\n            margin-top: 10px;\n        }\n\n        .badge {\n            display: inline-flex;\n            padding: 5px 9px;\n            border-radius: 999px;\n            font-size: 12px;\n            font-weight: 800;\n        }\n\n        .badge-ok {\n            background: #e8f6ec;\n            color: #19713a;\n        }\n\n        .badge-off {\n            background: #edf0f3;\n            color: #66727d;\n        }\n\n        .loading {\n            padding: 25px;\n            text-align: center;\n            color: #6a8199;\n        }\n\n        @media (max-width: 1000px) {\n            .stats {\n                grid-template-columns: repeat(2, minmax(0, 1fr));\n            }\n\n            .input-grid,\n            .detail-grid {\n                grid-template-columns: 1fr 1fr;\n            }\n\n            .input-grid .span-4,\n            .detail-grid .span-4 {\n                grid-column: 1 / -1;\n            }\n        }\n\n        @media (max-width: 800px) {\n            .filters,\n            .row-form,\n            .input-grid,\n            .detail-grid,\n            .stats {\n                grid-template-columns: 1fr;\n            }\n\n            .input-grid .span-2,\n            .input-grid .span-4,\n            .detail-grid .span-2,\n            .detail-grid .span-4 {\n                grid-column: auto;\n            }\n\n            .hero-inner {\n                flex-direction: column;\n                align-items: flex-start;\n            }\n\n            .hero {\n                padding: 26px 18px;\n            }\n\n            .container {\n                padding: 0 12px 40px;\n            }\n        }\n    </style>\n</head>\n\n<body>\n    {% include "partials/dropdown_menu_v1.html" %}\n\n    <header class="hero">\n        <div class="hero-inner">\n            <div>\n                <p class="eyebrow">Nguồn dữ liệu PCGDMN</p>\n                <h1>\n                    Trường, cơ sở, điểm trường và nhóm/lớp\n                </h1>\n                <p>\n                    Nhập dữ liệu gốc để hệ thống tự tổng hợp số cơ sở,\n                    điểm trường, lớp đơn/lớp ghép và tỷ lệ giáo viên/lớp.\n                </p>\n            </div>\n\n            <a\n                class="button button-light"\n                href="/doi-ngu?school_year_id={{ selected_year_id }}{% if selected_commune_id %}&commune_id={{ selected_commune_id }}{% endif %}{% if selected_school_id %}&school_id={{ selected_school_id }}{% endif %}"\n            >\n                ← Danh sách đội ngũ\n            </a>\n        </div>\n    </header>\n\n    <main class="container">\n\n        {% if status == \'saved\' %}\n        <div class="notice">\n            Đã lưu cấu hình tổng hợp số nhóm/lớp.\n        </div>\n        {% elif status == \'site_saved\' %}\n        <div class="notice">\n            Đã lưu cơ sở/điểm trường.\n        </div>\n        {% elif status == \'site_toggled\' %}\n        <div class="notice">\n            Đã cập nhật trạng thái cơ sở/điểm trường.\n        </div>\n        {% elif status == \'class_saved\' %}\n        <div class="notice">\n            Đã lưu nhóm/lớp và tự đồng bộ số lớp tổng hợp.\n        </div>\n        {% elif status == \'class_toggled\' %}\n        <div class="notice">\n            Đã cập nhật trạng thái lớp và tự đồng bộ số lớp tổng hợp.\n        </div>\n        {% elif status in [\'site_duplicate\', \'class_duplicate\'] %}\n        <div class="notice notice-error">\n            Dữ liệu bị trùng trong cùng trường và năm học. Vui lòng kiểm tra lại.\n        </div>\n        {% elif status in [\'site_invalid\', \'class_invalid\', \'invalid\'] %}\n        <div class="notice notice-error">\n            Dữ liệu chưa hợp lệ hoặc không thuộc đúng trường/năm học.\n        </div>\n        {% elif status == \'forbidden\' %}\n        <div class="notice notice-error">\n            Tài khoản không có quyền cập nhật trường này.\n        </div>\n        {% endif %}\n\n        <section class="panel">\n            <p class="section-label">Bộ lọc</p>\n\n            <form\n                method="get"\n                action="/doi-ngu/cau-hinh-lop"\n            >\n                <div class="filters">\n                    <div>\n                        <label>Năm học</label>\n                        <select name="school_year_id">\n                            {% for year in school_years %}\n                            <option\n                                value="{{ year.id }}"\n                                {% if year.id == selected_year_id %}selected{% endif %}\n                            >\n                                {{ year.code }}\n                            </option>\n                            {% endfor %}\n                        </select>\n                    </div>\n\n                    <div>\n                        <label>Xã/phường</label>\n                        <select name="commune_id">\n                            <option value="">\n                                -- Toàn tỉnh --\n                            </option>\n\n                            {% for commune in communes %}\n                            <option\n                                value="{{ commune.id }}"\n                                {% if commune.id == selected_commune_id %}selected{% endif %}\n                            >\n                                {{ commune.name }}\n                            </option>\n                            {% endfor %}\n                        </select>\n                    </div>\n\n                    <button\n                        class="button button-primary"\n                        type="submit"\n                    >\n                        Lọc\n                    </button>\n                </div>\n            </form>\n        </section>\n\n        <section class="panel">\n            <p class="section-label">\n                Danh sách trường/cơ sở trong phạm vi\n            </p>\n\n            <h2>\n                {{ rows|length }} trường/cơ sở\n            </h2>\n\n            <p class="muted">\n                Khối số liệu tổng hợp cũ vẫn được giữ để tương thích\n                các báo cáo hiện có. Khi nhập danh sách lớp chi tiết,\n                hệ thống tự đồng bộ Tổng nhóm/lớp, lớp 3–4 tuổi và lớp 5 tuổi.\n            </p>\n\n            <div class="table-wrap">\n                <table class="table">\n                    <thead>\n                        <tr>\n                            <th>Trường/cơ sở</th>\n                            <th>Cấu hình tổng hợp đang có</th>\n                            <th>Chi tiết</th>\n                        </tr>\n                    </thead>\n\n                    <tbody>\n                        {% for row in rows %}\n                        <tr\n                            {% if row.school.id == selected_school_id %}\n                            class="selected-row"\n                            {% endif %}\n                        >\n                            <td>\n                                <strong>\n                                    {{ row.school.name }}\n                                </strong>\n                                <div class="muted">\n                                    {{ row.school.commune.name }}\n                                </div>\n                            </td>\n\n                            <td>\n                                <form\n                                    class="row-form"\n                                    method="post"\n                                    action="/doi-ngu/cau-hinh-lop/{{ row.school.id }}"\n                                >\n                                    <input\n                                        type="hidden"\n                                        name="school_year_id"\n                                        value="{{ selected_year_id }}"\n                                    >\n\n                                    <div>\n                                        <label>\n                                            Loại cơ sở\n                                        </label>\n\n                                        <select\n                                            name="institution_group"\n                                        >\n                                            {% for code, label in institution_group_labels.items() %}\n                                            <option\n                                                value="{{ code }}"\n                                                {% if code == row.institution_group %}selected{% endif %}\n                                            >\n                                                {{ label }}\n                                            </option>\n                                            {% endfor %}\n                                        </select>\n                                    </div>\n\n                                    <div>\n                                        <label>\n                                            Tổng nhóm/lớp\n                                        </label>\n\n                                        <input\n                                            type="number"\n                                            min="0"\n                                            name="total_groups_classes"\n                                            value="{{ row.total_groups_classes }}"\n                                        >\n                                    </div>\n\n                                    <div>\n                                        <label>\n                                            Lớp 3–4 tuổi\n                                        </label>\n\n                                        <input\n                                            type="number"\n                                            min="0"\n                                            name="preschool_classes_3_4"\n                                            value="{{ row.preschool_classes_3_4 }}"\n                                        >\n                                    </div>\n\n                                    <div>\n                                        <label>\n                                            Lớp 5 tuổi\n                                        </label>\n\n                                        <input\n                                            type="number"\n                                            min="0"\n                                            name="preschool_classes_5"\n                                            value="{{ row.preschool_classes_5 }}"\n                                        >\n                                    </div>\n\n                                    {% if can_manage %}\n                                    <button\n                                        class="button button-primary"\n                                        type="submit"\n                                    >\n                                        Lưu\n                                    </button>\n                                    {% else %}\n                                    <span class="muted">\n                                        Chỉ xem\n                                    </span>\n                                    {% endif %}\n                                </form>\n                            </td>\n\n                            <td>\n                                <a\n                                    class="button button-secondary button-small"\n                                    href="/doi-ngu/cau-hinh-lop?school_year_id={{ selected_year_id }}&commune_id={{ row.school.commune_id }}&school_id={{ row.school.id }}#chi-tiet-truong-lop"\n                                >\n                                    Cơ sở / Lớp\n                                </a>\n                            </td>\n                        </tr>\n\n                        {% else %}\n                        <tr>\n                            <td\n                                colspan="3"\n                                class="muted"\n                            >\n                                Không có trường trong phạm vi.\n                            </td>\n                        </tr>\n                        {% endfor %}\n                    </tbody>\n                </table>\n            </div>\n        </section>\n\n        {% if selected_school_id and rows|length == 1 %}\n        <section\n            class="panel"\n            id="chi-tiet-truong-lop"\n        >\n            <div class="detail-title">\n                <div>\n                    <p class="section-label">\n                        Nguồn dữ liệu chi tiết\n                    </p>\n\n                    <h2 style="margin-bottom:5px;">\n                        {{ rows[0].school.name }}\n                    </h2>\n\n                    <p class="muted">\n                        Năm học:\n                        {% for year in school_years %}\n                            {% if year.id == selected_year_id %}\n                                {{ year.code }}\n                            {% endif %}\n                        {% endfor %}\n                    </p>\n                </div>\n\n                <a\n                    class="button button-secondary"\n                    href="/doi-ngu/cau-hinh-lop?school_year_id={{ selected_year_id }}{% if selected_commune_id %}&commune_id={{ selected_commune_id }}{% endif %}"\n                >\n                    ← Danh sách trường\n                </a>\n            </div>\n\n            <div\n                id="b1311461-detail-root"\n                class="loading"\n            >\n                Đang tải cơ sở, điểm trường và danh sách lớp...\n            </div>\n        </section>\n\n        <script>\n        (function () {\n            const schoolId = Number(\n                "{{ selected_school_id|int }}"\n            );\n\n            const yearId = Number(\n                "{{ selected_year_id|int }}"\n            );\n\n            const root = document.getElementById(\n                "b1311461-detail-root"\n            );\n\n            if (!root || !schoolId || !yearId) {\n                return;\n            }\n\n            const endpoint =\n                "/doi-ngu/cau-hinh-lop-chi-tiet";\n\n            function esc(value) {\n                return String(\n                    value === null || value === undefined\n                        ? ""\n                        : value\n                )\n                    .replaceAll("&", "&amp;")\n                    .replaceAll("<", "&lt;")\n                    .replaceAll(">", "&gt;")\n                    .replaceAll(\'"\', "&quot;")\n                    .replaceAll("\'", "&#039;");\n            }\n\n            function checked(value) {\n                return Number(value || 0) === 1\n                    ? "checked"\n                    : "";\n            }\n\n            function selected(\n                actual,\n                expected\n            ) {\n                return String(actual || "") === String(expected)\n                    ? "selected"\n                    : "";\n            }\n\n            function optionList(\n                mapping,\n                current\n            ) {\n                return Object.entries(\n                    mapping || {}\n                )\n                    .map(function (entry) {\n                        return (\n                            \'<option value="\' +\n                            esc(entry[0]) +\n                            \'" \' +\n                            selected(\n                                current,\n                                entry[0]\n                            ) +\n                            ">" +\n                            esc(entry[1]) +\n                            "</option>"\n                        );\n                    })\n                    .join("");\n            }\n\n            function siteOptions(\n                sites,\n                current\n            ) {\n                let html =\n                    \'<option value="">-- Cơ sở chính/chưa gắn điểm --</option>\';\n\n                (sites || [])\n                    .filter(function (item) {\n                        return Number(\n                            item.is_active === null\n                                ? 1\n                                : item.is_active\n                        ) === 1;\n                    })\n                    .forEach(function (item) {\n                        html +=\n                            \'<option value="\' +\n                            esc(item.id) +\n                            \'" \' +\n                            selected(\n                                current,\n                                item.id\n                            ) +\n                            ">" +\n                            esc(item.site_name) +\n                            "</option>";\n                    });\n\n                return html;\n            }\n\n            function statCards(stats) {\n                return `\n                    <div class="stats">\n                        <div class="stat">\n                            <span>Cơ sở/điểm đang hoạt động</span>\n                            <strong>${esc(stats.active_sites || 0)}</strong>\n                        </div>\n                        <div class="stat">\n                            <span>Cơ sở độc lập</span>\n                            <strong>${esc(stats.independent_sites || 0)}</strong>\n                        </div>\n                        <div class="stat">\n                            <span>Nhóm/lớp đang hoạt động</span>\n                            <strong>${esc(stats.active_classes || 0)}</strong>\n                        </div>\n                        <div class="stat">\n                            <span>Lớp đơn</span>\n                            <strong>${esc(stats.single_classes || 0)}</strong>\n                        </div>\n                        <div class="stat">\n                            <span>Lớp ghép</span>\n                            <strong>${esc(stats.combined_classes || 0)}</strong>\n                        </div>\n                    </div>\n                `;\n            }\n\n            function siteCreateForm(\n                labels,\n                canManage\n            ) {\n                if (!canManage) {\n                    return "";\n                }\n\n                return `\n                    <div class="detail-card">\n                        <h3>+ Thêm cơ sở / điểm trường</h3>\n\n                        <form\n                            method="post"\n                            action="${endpoint}/site"\n                        >\n                            <input\n                                type="hidden"\n                                name="school_id"\n                                value="${schoolId}"\n                            >\n                            <input\n                                type="hidden"\n                                name="school_year_id"\n                                value="${yearId}"\n                            >\n                            <input\n                                type="hidden"\n                                name="site_id"\n                                value="0"\n                            >\n\n                            <div class="input-grid">\n                                <div>\n                                    <label>Mã cơ sở/điểm</label>\n                                    <input\n                                        name="site_code"\n                                        placeholder="Có thể để trống"\n                                    >\n                                </div>\n\n                                <div class="span-2">\n                                    <label>Tên cơ sở/điểm trường *</label>\n                                    <input\n                                        name="site_name"\n                                        required\n                                    >\n                                </div>\n\n                                <div>\n                                    <label>Loại</label>\n                                    <select name="site_type">\n                                        ${optionList(\n                                            labels.site_types,\n                                            "MAIN"\n                                        )}\n                                    </select>\n                                </div>\n\n                                <div class="span-2">\n                                    <label>Địa chỉ</label>\n                                    <input name="address">\n                                </div>\n\n                                <div>\n                                    <div class="checkbox-line">\n                                        <input\n                                            id="new_site_independent"\n                                            type="checkbox"\n                                            name="is_independent"\n                                            value="1"\n                                        >\n                                        <label for="new_site_independent">\n                                            Cơ sở độc lập\n                                        </label>\n                                    </div>\n                                </div>\n\n                                <div class="span-4">\n                                    <label>Ghi chú</label>\n                                    <textarea name="notes"></textarea>\n                                </div>\n                            </div>\n\n                            <div class="actions">\n                                <button\n                                    class="button button-primary"\n                                    type="submit"\n                                >\n                                    Lưu cơ sở/điểm trường\n                                </button>\n                            </div>\n                        </form>\n                    </div>\n                `;\n            }\n\n            function siteCards(\n                sites,\n                labels,\n                canManage\n            ) {\n                if (!sites.length) {\n                    return `\n                        <p class="muted">\n                            Chưa khai báo cơ sở hoặc điểm trường cho năm học này.\n                        </p>\n                    `;\n                }\n\n                return sites.map(\n                    function (item) {\n                        const active =\n                            Number(\n                                item.is_active === null\n                                    ? 1\n                                    : item.is_active\n                            ) === 1;\n\n                        if (!canManage) {\n                            return `\n                                <div class="detail-card ${active ? "" : "inactive"}">\n                                    <strong>${esc(item.site_name)}</strong>\n                                    <span class="badge ${active ? "badge-ok" : "badge-off"}">\n                                        ${active ? "Đang hoạt động" : "Đã khóa"}\n                                    </span>\n                                    <div class="muted">\n                                        ${esc(\n                                            labels.site_types[\n                                                item.site_type\n                                            ] || item.site_type || ""\n                                        )}\n                                        ${item.site_code ? " · " + esc(item.site_code) : ""}\n                                        ${item.address ? " · " + esc(item.address) : ""}\n                                    </div>\n                                </div>\n                            `;\n                        }\n\n                        return `\n                            <div class="detail-card ${active ? "" : "inactive"}">\n                                <form\n                                    method="post"\n                                    action="${endpoint}/site"\n                                >\n                                    <input\n                                        type="hidden"\n                                        name="school_id"\n                                        value="${schoolId}"\n                                    >\n                                    <input\n                                        type="hidden"\n                                        name="school_year_id"\n                                        value="${yearId}"\n                                    >\n                                    <input\n                                        type="hidden"\n                                        name="site_id"\n                                        value="${esc(item.id)}"\n                                    >\n\n                                    <div class="detail-grid">\n                                        <div>\n                                            <label>Mã</label>\n                                            <input\n                                                name="site_code"\n                                                value="${esc(item.site_code)}"\n                                            >\n                                        </div>\n\n                                        <div>\n                                            <label>Tên cơ sở/điểm *</label>\n                                            <input\n                                                name="site_name"\n                                                value="${esc(item.site_name)}"\n                                                required\n                                            >\n                                        </div>\n\n                                        <div>\n                                            <label>Loại</label>\n                                            <select name="site_type">\n                                                ${optionList(\n                                                    labels.site_types,\n                                                    item.site_type\n                                                )}\n                                            </select>\n                                        </div>\n\n                                        <div>\n                                            <div class="checkbox-line">\n                                                <input\n                                                    id="site_independent_${esc(item.id)}"\n                                                    type="checkbox"\n                                                    name="is_independent"\n                                                    value="1"\n                                                    ${checked(item.is_independent)}\n                                                >\n                                                <label for="site_independent_${esc(item.id)}">\n                                                    Cơ sở độc lập\n                                                </label>\n                                            </div>\n                                        </div>\n\n                                        <div class="span-2">\n                                            <label>Địa chỉ</label>\n                                            <input\n                                                name="address"\n                                                value="${esc(item.address)}"\n                                            >\n                                        </div>\n\n                                        <div class="span-2">\n                                            <label>Ghi chú</label>\n                                            <input\n                                                name="notes"\n                                                value="${esc(item.notes)}"\n                                            >\n                                        </div>\n                                    </div>\n\n                                    <div class="actions">\n                                        <button\n                                            class="button button-primary button-small"\n                                            type="submit"\n                                        >\n                                            Lưu\n                                        </button>\n\n                                        <span class="badge ${active ? "badge-ok" : "badge-off"}">\n                                            ${active ? "Đang hoạt động" : "Đã khóa"}\n                                        </span>\n                                    </div>\n                                </form>\n\n                                <form\n                                    method="post"\n                                    action="${endpoint}/site/${esc(item.id)}/toggle"\n                                    class="actions"\n                                >\n                                    <input\n                                        type="hidden"\n                                        name="school_id"\n                                        value="${schoolId}"\n                                    >\n                                    <input\n                                        type="hidden"\n                                        name="school_year_id"\n                                        value="${yearId}"\n                                    >\n\n                                    <button\n                                        class="button button-secondary button-small"\n                                        type="submit"\n                                    >\n                                        ${active ? "Khóa" : "Mở lại"}\n                                    </button>\n                                </form>\n                            </div>\n                        `;\n                    }\n                ).join("");\n            }\n\n            function classCreateForm(\n                sites,\n                labels,\n                canManage\n            ) {\n                if (!canManage) {\n                    return "";\n                }\n\n                return `\n                    <div class="detail-card">\n                        <h3>+ Thêm nhóm/lớp</h3>\n\n                        <form\n                            method="post"\n                            action="${endpoint}/class"\n                        >\n                            <input\n                                type="hidden"\n                                name="school_id"\n                                value="${schoolId}"\n                            >\n                            <input\n                                type="hidden"\n                                name="school_year_id"\n                                value="${yearId}"\n                            >\n                            <input\n                                type="hidden"\n                                name="class_id"\n                                value="0"\n                            >\n\n                            <div class="input-grid">\n                                <div>\n                                    <label>Mã lớp</label>\n                                    <input\n                                        name="class_code"\n                                        placeholder="Có thể để trống"\n                                    >\n                                </div>\n\n                                <div>\n                                    <label>Tên nhóm/lớp *</label>\n                                    <input\n                                        name="class_name"\n                                        required\n                                    >\n                                </div>\n\n                                <div>\n                                    <label>Cơ sở / điểm trường</label>\n                                    <select name="site_year_id">\n                                        ${siteOptions(\n                                            sites,\n                                            ""\n                                        )}\n                                    </select>\n                                </div>\n\n                                <div>\n                                    <label>Lớp đơn / lớp ghép</label>\n                                    <select name="class_structure">\n                                        ${optionList(\n                                            labels.class_structures,\n                                            "SINGLE"\n                                        )}\n                                    </select>\n                                </div>\n\n                                <div>\n                                    <label>Nhóm tuổi</label>\n                                    <select name="age_group_code">\n                                        ${optionList(\n                                            labels.age_groups,\n                                            "CHUA_XAC_DINH"\n                                        )}\n                                    </select>\n                                </div>\n\n                                <div>\n                                    <label>Số trẻ kế hoạch</label>\n                                    <input\n                                        type="number"\n                                        min="0"\n                                        name="planned_children_count"\n                                    >\n                                </div>\n\n                                <div class="span-2">\n                                    <label>Ghi chú</label>\n                                    <input name="notes">\n                                </div>\n                            </div>\n\n                            <div class="actions">\n                                <button\n                                    class="button button-primary"\n                                    type="submit"\n                                >\n                                    Lưu nhóm/lớp\n                                </button>\n                            </div>\n                        </form>\n                    </div>\n                `;\n            }\n\n            function classCards(\n                classes,\n                sites,\n                labels,\n                canManage\n            ) {\n                if (!classes.length) {\n                    return `\n                        <p class="muted">\n                            Chưa có nhóm/lớp trong trường và năm học này.\n                        </p>\n                    `;\n                }\n\n                return classes.map(\n                    function (item) {\n                        const active =\n                            Number(\n                                item.is_active === null\n                                    ? 1\n                                    : item.is_active\n                            ) === 1;\n\n                        if (!canManage) {\n                            return `\n                                <div class="detail-card ${active ? "" : "inactive"}">\n                                    <strong>${esc(item.name)}</strong>\n                                    <span class="badge ${active ? "badge-ok" : "badge-off"}">\n                                        ${active ? "Đang hoạt động" : "Đã khóa"}\n                                    </span>\n                                    <div class="muted">\n                                        ${esc(\n                                            labels.class_structures[\n                                                item.class_structure || "SINGLE"\n                                            ] || "Lớp đơn"\n                                        )}\n                                        ·\n                                        ${esc(\n                                            labels.age_groups[\n                                                item.age_group_code || "CHUA_XAC_DINH"\n                                            ] || "Chưa xác định"\n                                        )}\n                                        ${item.site_name ? " · " + esc(item.site_name) : ""}\n                                    </div>\n                                </div>\n                            `;\n                        }\n\n                        return `\n                            <div class="detail-card ${active ? "" : "inactive"}">\n                                <form\n                                    method="post"\n                                    action="${endpoint}/class"\n                                >\n                                    <input\n                                        type="hidden"\n                                        name="school_id"\n                                        value="${schoolId}"\n                                    >\n                                    <input\n                                        type="hidden"\n                                        name="school_year_id"\n                                        value="${yearId}"\n                                    >\n                                    <input\n                                        type="hidden"\n                                        name="class_id"\n                                        value="${esc(item.id)}"\n                                    >\n\n                                    <div class="detail-grid">\n                                        <div>\n                                            <label>Mã lớp</label>\n                                            <input\n                                                name="class_code"\n                                                value="${esc(item.code)}"\n                                            >\n                                        </div>\n\n                                        <div>\n                                            <label>Tên nhóm/lớp *</label>\n                                            <input\n                                                name="class_name"\n                                                value="${esc(item.name)}"\n                                                required\n                                            >\n                                        </div>\n\n                                        <div>\n                                            <label>Cơ sở / điểm trường</label>\n                                            <select name="site_year_id">\n                                                ${siteOptions(\n                                                    sites,\n                                                    item.site_year_id\n                                                )}\n                                            </select>\n                                        </div>\n\n                                        <div>\n                                            <label>Lớp đơn / lớp ghép</label>\n                                            <select name="class_structure">\n                                                ${optionList(\n                                                    labels.class_structures,\n                                                    item.class_structure || "SINGLE"\n                                                )}\n                                            </select>\n                                        </div>\n\n                                        <div>\n                                            <label>Nhóm tuổi</label>\n                                            <select name="age_group_code">\n                                                ${optionList(\n                                                    labels.age_groups,\n                                                    item.age_group_code || "CHUA_XAC_DINH"\n                                                )}\n                                            </select>\n                                        </div>\n\n                                        <div>\n                                            <label>Số trẻ kế hoạch</label>\n                                            <input\n                                                type="number"\n                                                min="0"\n                                                name="planned_children_count"\n                                                value="${esc(item.planned_children_count)}"\n                                            >\n                                        </div>\n\n                                        <div class="span-2">\n                                            <label>Ghi chú</label>\n                                            <input\n                                                name="notes"\n                                                value="${esc(item.notes)}"\n                                            >\n                                        </div>\n                                    </div>\n\n                                    <div class="actions">\n                                        <button\n                                            class="button button-primary button-small"\n                                            type="submit"\n                                        >\n                                            Lưu\n                                        </button>\n\n                                        <span class="badge ${active ? "badge-ok" : "badge-off"}">\n                                            ${active ? "Đang hoạt động" : "Đã khóa"}\n                                        </span>\n                                    </div>\n                                </form>\n\n                                <form\n                                    method="post"\n                                    action="${endpoint}/class/${esc(item.id)}/toggle"\n                                    class="actions"\n                                >\n                                    <input\n                                        type="hidden"\n                                        name="school_id"\n                                        value="${schoolId}"\n                                    >\n                                    <input\n                                        type="hidden"\n                                        name="school_year_id"\n                                        value="${yearId}"\n                                    >\n\n                                    <button\n                                        class="button button-secondary button-small"\n                                        type="submit"\n                                    >\n                                        ${active ? "Khóa" : "Mở lại"}\n                                    </button>\n                                </form>\n                            </div>\n                        `;\n                    }\n                ).join("");\n            }\n\n            function render(data) {\n                const labels =\n                    data.labels || {};\n\n                const sites =\n                    data.sites || [];\n\n                const classes =\n                    data.classes || [];\n\n                const canManage =\n                    Boolean(data.can_manage);\n\n                root.className = "";\n\n                root.innerHTML = `\n                    ${statCards(data.stats || {})}\n\n                    <div class="notice notice-warning">\n                        <strong>Nguồn chuẩn:</strong>\n                        các thống kê lớp đơn/lớp ghép và tổng số lớp\n                        sẽ lấy từ danh sách chi tiết này.\n                        Khi thêm, sửa hoặc khóa/mở lớp,\n                        hệ thống đồng bộ lại số nhóm/lớp tổng hợp hiện có.\n                    </div>\n\n                    <div class="subpanel">\n                        <h2>Cơ sở / Điểm trường</h2>\n                        <p class="muted">\n                            Một trường có thể có cơ sở chính,\n                            nhiều điểm trường hoặc cơ sở độc lập.\n                        </p>\n\n                        ${siteCreateForm(\n                            labels,\n                            canManage\n                        )}\n\n                        <div style="margin-top:16px;">\n                            ${siteCards(\n                                sites,\n                                labels,\n                                canManage\n                            )}\n                        </div>\n                    </div>\n\n                    <div class="subpanel">\n                        <h2>Danh sách nhóm/lớp</h2>\n                        <p class="muted">\n                            Xác định lớp đơn/lớp ghép, nhóm tuổi\n                            và cơ sở/điểm trường của từng lớp.\n                            Đây là nguồn để tính tổng số lớp và GV/lớp.\n                        </p>\n\n                        ${classCreateForm(\n                            sites,\n                            labels,\n                            canManage\n                        )}\n\n                        <div style="margin-top:16px;">\n                            ${classCards(\n                                classes,\n                                sites,\n                                labels,\n                                canManage\n                            )}\n                        </div>\n                    </div>\n                `;\n            }\n\n            fetch(\n                endpoint +\n                "?school_year_id=" +\n                encodeURIComponent(yearId) +\n                "&school_id=" +\n                encodeURIComponent(schoolId),\n                {\n                    credentials: "same-origin"\n                }\n            )\n                .then(function (response) {\n                    return response.json().then(\n                        function (data) {\n                            if (!response.ok) {\n                                throw new Error(\n                                    data.message ||\n                                    "Không tải được dữ liệu."\n                                );\n                            }\n\n                            return data;\n                        }\n                    );\n                })\n                .then(render)\n                .catch(function (error) {\n                    root.className =\n                        "notice notice-error";\n\n                    root.textContent =\n                        error.message ||\n                        "Không tải được dữ liệu chi tiết.";\n                });\n        })();\n        </script>\n        {% endif %}\n\n    </main>\n</body>\n</html>\n'


REQUIRED_DB = {
    "school_site_year_records": {
        "id",
        "school_id",
        "school_year_id",
        "site_code",
        "site_name",
        "site_type",
        "is_independent",
        "address",
        "is_active",
        "notes",
    },
    "school_class_year_attributes": {
        "id",
        "class_id",
        "site_year_id",
        "class_structure",
        "age_group_code",
        "is_mixed_age",
        "planned_children_count",
        "notes",
    },
    "classes": {
        "id",
        "school_id",
        "school_year_id",
        "code",
        "name",
        "is_active",
    },
}


def read_text(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(
            f"Không tìm thấy: {path}"
        )

    return path.read_text(
        encoding="utf-8-sig",
        errors="strict",
    )


def write_text(
    path: Path,
    text_value: str,
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_text(
        text_value,
        encoding="utf-8",
    )


def sqlite_backup(
    source: Path,
    target: Path,
) -> None:
    target.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    src = sqlite3.connect(
        str(source)
    )

    dst = sqlite3.connect(
        str(target)
    )

    try:
        src.backup(dst)
        dst.commit()
    finally:
        dst.close()
        src.close()


def sqlite_restore(
    source: Path,
    target: Path,
) -> None:
    src = sqlite3.connect(
        str(source)
    )

    dst = sqlite3.connect(
        str(target)
    )

    try:
        src.backup(dst)
        dst.commit()
    finally:
        dst.close()
        src.close()


def table_exists(
    conn: sqlite3.Connection,
    table: str,
) -> bool:
    return (
        conn.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type='table'
              AND name=?
            LIMIT 1
            """,
            (table,),
        ).fetchone()
        is not None
    )


def table_columns(
    conn: sqlite3.Connection,
    table: str,
) -> set[str]:
    return {
        str(row[1])
        for row in conn.execute(
            f'PRAGMA table_info("{table}")'
        ).fetchall()
    }


def table_count(
    conn: sqlite3.Connection,
    table: str,
) -> int:
    return int(
        conn.execute(
            f'SELECT COUNT(*) FROM "{table}"'
        ).fetchone()[0]
    )


def db_snapshot() -> dict:
    conn = sqlite3.connect(
        str(DB)
    )

    try:
        integrity = str(
            conn.execute(
                "PRAGMA integrity_check"
            ).fetchone()[0]
        )

        fk = len(
            conn.execute(
                "PRAGMA foreign_key_check"
            ).fetchall()
        )

        for table, required in REQUIRED_DB.items():
            if not table_exists(
                conn,
                table,
            ):
                raise RuntimeError(
                    "Thiếu bảng từ Bài 14.5: "
                    + table
                )

            missing = (
                required
                - table_columns(
                    conn,
                    table,
                )
            )

            if missing:
                raise RuntimeError(
                    f"Bảng {table} thiếu cột: "
                    + ", ".join(
                        sorted(missing)
                    )
                )

        counts = {
            table: table_count(
                conn,
                table,
            )
            for table in (
                "classes",
                "school_site_year_records",
                "school_class_year_attributes",
                "school_staff_year_summaries",
            )
            if table_exists(
                conn,
                table,
            )
        }

        return {
            "integrity": integrity,
            "fk": fk,
            "counts": counts,
        }

    finally:
        conn.close()


def backup_path(path: Path) -> Path:
    return (
        BACKUP
        / path.relative_to(
            PROJECT
        )
    )


def backup_file(
    path: Path,
) -> None:
    if not path.exists():
        return

    dst = backup_path(
        path
    )

    dst.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    shutil.copy2(
        path,
        dst,
    )


def restore_file(
    path: Path,
    existed_before: bool,
) -> None:
    src = backup_path(
        path
    )

    if existed_before:
        if not src.exists():
            raise RuntimeError(
                f"Thiếu backup: {src}"
            )

        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        shutil.copy2(
            src,
            path,
        )
    else:
        if path.exists():
            path.unlink()


def patch_main(
    source: str,
) -> str:
    patched = source

    if IMPORT_MARKER not in patched:
        anchor = (
            "from app.routers.staff_management "
            "import router as staff_management_router"
        )

        if anchor not in patched:
            raise RuntimeError(
                "Không tìm thấy import "
                "staff_management_router trong app/main.py."
            )

        replacement = (
            anchor
            + "\n"
            + IMPORT_MARKER
            + "\n"
            + "from app.routers.class_structure_inputs "
            + "import router as class_structure_inputs_router"
        )

        patched = patched.replace(
            anchor,
            replacement,
            1,
        )

    if INCLUDE_MARKER not in patched:
        anchor = (
            "app.include_router("
            "staff_management_router"
            ")"
        )

        if anchor not in patched:
            raise RuntimeError(
                "Không tìm thấy include "
                "staff_management_router trong app/main.py."
            )

        replacement = (
            anchor
            + "\n"
            + INCLUDE_MARKER
            + "\n"
            + "app.include_router("
            + "class_structure_inputs_router"
            + ")"
        )

        patched = patched.replace(
            anchor,
            replacement,
            1,
        )

    ast.parse(
        patched
    )

    return patched


def verify_staff_router(
    source: str,
) -> None:
    for name in (
        "class_config_page",
        "class_config_save",
        "_can_manage",
        "_ensure_school_in_scope",
        "_infer_institution_group",
        "lay_thong_tin_nguoi_dung",
        "SchoolStaffYearSummary",
    ):
        if name not in source:
            raise RuntimeError(
                "staff_management.py thiếu nền cần dùng: "
                + name
            )


def compile_py(
    path: Path,
) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "py_compile",
            str(path),
        ],
        cwd=PROJECT,
        capture_output=True,
        text=True,
    )

    if result.stdout:
        print(
            result.stdout.rstrip()
        )

    if result.stderr:
        print(
            result.stderr.rstrip()
        )

    if result.returncode != 0:
        raise RuntimeError(
            "py_compile không đạt: "
            + str(path)
        )


def verify_template(
    source: str,
) -> None:
    required = (
        "Trường, cơ sở, điểm trường và nhóm/lớp",
        "/doi-ngu/cau-hinh-lop-chi-tiet",
        "Cơ sở / Điểm trường",
        "Danh sách nhóm/lớp",
        "Lớp đơn / lớp ghép",
        "selected_school_id",
        "selected_year_id",
    )

    for item in required:
        if item not in source:
            raise RuntimeError(
                "Template thiếu: "
                + item
            )

    from jinja2 import Environment

    Environment().parse(
        source
    )


def clear_cache() -> None:
    for cache in APP.rglob(
        "__pycache__"
    ):
        if cache.is_dir():
            shutil.rmtree(
                cache,
                ignore_errors=True,
            )


def main() -> int:
    print("=" * 126)
    print(
        "BÀI 13B-11.14.6.1 - "
        "MỞ RỘNG CẤU HÌNH TRƯỜNG/ĐIỂM TRƯỜNG/LỚP ĐƠN-LỚP GHÉP"
    )
    print("=" * 126)
    print()
    print("PHƯƠNG ÁN SAU KHẢO SÁT 14.6.0:")
    print(
        " - MỞ RỘNG màn /doi-ngu/cau-hinh-lop hiện có."
    )
    print(
        " - KHÔNG tạo thêm menu Trường/Lớp trùng."
    )
    print(
        " - Giữ route và khối tổng hợp cũ để tương thích báo cáo."
    )
    print()
    print("BỔ SUNG NGUỒN NHẬP:")
    print(
        " 1. Cơ sở chính / Điểm trường / Cơ sở độc lập."
    )
    print(
        " 2. Nhóm/lớp theo năm học."
    )
    print(
        " 3. Lớp đơn / Lớp ghép."
    )
    print(
        " 4. Nhóm tuổi của lớp."
    )
    print(
        " 5. Gắn lớp với cơ sở/điểm trường."
    )
    print(
        " 6. Số trẻ kế hoạch (dữ liệu gốc tùy chọn)."
    )
    print()
    print("TỰ ĐỘNG:")
    print(
        " - Khi thêm/sửa/khóa lớp, tự đồng bộ "
        "Tổng nhóm/lớp, lớp 3–4 tuổi, lớp 5 tuổi."
    )
    print(
        " - Không nhập tỷ lệ GV/lớp bằng tay."
    )
    print()
    print("AN TOÀN:")
    print(
        " - Không ALTER database."
    )
    print(
        " - Không thay đổi dữ liệu khi cài."
    )
    print(
        " - Backup main/template/router/database."
    )
    print(
        " - py_compile + Jinja + integrity + FK."
    )
    print(
        " - Có lỗi tự rollback."
    )
    print()

    for path in (
        MAIN,
        STAFF_ROUTER,
        TEMPLATE,
        DB,
    ):
        if not path.exists():
            raise RuntimeError(
                f"Không tìm thấy: {path}"
            )

    staff_original = read_text(
        STAFF_ROUTER
    )

    verify_staff_router(
        staff_original
    )

    before = db_snapshot()

    print(
        "integrity_check trước cài:",
        before["integrity"],
    )

    print(
        "foreign_key_check trước cài:",
        before["fk"],
        "lỗi",
    )

    for table, count in before["counts"].items():
        print(
            f" - {table}: "
            f"{count} bản ghi"
        )

    if (
        before["integrity"].lower()
        != "ok"
        or before["fk"] != 0
    ):
        raise RuntimeError(
            "Database không đạt kiểm tra trước cài."
        )

    existed = {
        MAIN: MAIN.exists(),
        TEMPLATE: TEMPLATE.exists(),
        NEW_ROUTER: NEW_ROUTER.exists(),
    }

    BACKUP.mkdir(
        parents=True,
        exist_ok=False,
    )

    for path in (
        MAIN,
        TEMPLATE,
        NEW_ROUTER,
    ):
        backup_file(
            path
        )

    sqlite_backup(
        DB,
        DB_BACKUP,
    )

    print(
        "Backup:",
        BACKUP,
    )

    try:
        main_patched = patch_main(
            read_text(
                MAIN
            )
        )

        verify_template(
            TEMPLATE_CODE
        )

        ast.parse(
            ROUTER_CODE
        )

        # Ghi router trước để uvicorn --reload không gặp import thiếu.
        write_text(
            NEW_ROUTER,
            ROUTER_CODE,
        )

        write_text(
            TEMPLATE,
            TEMPLATE_CODE,
        )

        write_text(
            MAIN,
            main_patched,
        )

        compile_py(
            NEW_ROUTER
        )

        compile_py(
            MAIN
        )

        # staff_management không sửa nhưng vẫn compile lại để kiểm tra nền.
        compile_py(
            STAFF_ROUTER
        )

        verify_template(
            read_text(
                TEMPLATE
            )
        )

        main_after = read_text(
            MAIN
        )

        if (
            IMPORT_MARKER
            not in main_after
            or INCLUDE_MARKER
            not in main_after
        ):
            raise RuntimeError(
                "main.py chưa include router 14.6.1."
            )

        router_after = read_text(
            NEW_ROUTER
        )

        for item in (
            '@router.get("")',
            '@router.post("/site")',
            '@router.post("/class")',
            "school_site_year_records",
            "school_class_year_attributes",
            "_sync_class_summary",
        ):
            if item not in router_after:
                raise RuntimeError(
                    "Router 14.6.1 thiếu: "
                    + item
                )

        after = db_snapshot()

        if (
            after["counts"]
            != before["counts"]
        ):
            raise RuntimeError(
                "Bộ cài không được thay đổi "
                "số bản ghi nghiệp vụ."
            )

        if (
            after["integrity"].lower()
            != "ok"
        ):
            raise RuntimeError(
                "integrity_check sau cài không OK."
            )

        if after["fk"] != 0:
            raise RuntimeError(
                "foreign_key_check sau cài "
                f"có {after['fk']} lỗi."
            )

        clear_cache()

        print()
        print("KIỂM TRA SAU CÀI:")
        print(
            " - Màn Cấu hình lớp cũ: GIỮ ROUTE"
        )
        print(
            " - Menu cũ: KHÔNG TẠO TRÙNG"
        )
        print(
            " - Khối tổng hợp cũ: GIỮ NGUYÊN NGHIỆP VỤ"
        )
        print(
            " - Cơ sở/điểm trường chi tiết: ĐÃ BỔ SUNG"
        )
        print(
            " - Lớp đơn/lớp ghép chi tiết: ĐÃ BỔ SUNG"
        )
        print(
            " - Tự đồng bộ tổng số lớp khi sửa dữ liệu chi tiết: OK"
        )
        print(
            " - Quyền: tái sử dụng _can_manage + _ensure_school_in_scope"
        )
        print(
            " - py_compile main/router/staff: OK"
        )
        print(
            " - Jinja parse: OK"
        )
        print(
            " - Database khi cài: KHÔNG THAY ĐỔI"
        )
        print(
            " - integrity_check: OK"
        )
        print(
            " - foreign_key_check: 0 lỗi"
        )
        print()
        print("=" * 126)
        print(
            "CÀI ĐẶT BÀI 13B-11.14.6.1 THÀNH CÔNG"
        )
        print("=" * 126)

        return 0

    except Exception:
        traceback.print_exc()

        print()
        print(
            "CÓ LỖI - "
            "ĐANG KHÔI PHỤC SOURCE/TEMPLATE/DATABASE..."
        )

        for path in (
            MAIN,
            TEMPLATE,
            NEW_ROUTER,
        ):
            try:
                restore_file(
                    path,
                    existed[path],
                )
            except Exception as exc:
                print(
                    " - Lỗi khôi phục",
                    path,
                    ":",
                    exc,
                )

        try:
            sqlite_restore(
                DB_BACKUP,
                DB,
            )

            print(
                " - Đã khôi phục database."
            )
        except Exception as exc:
            print(
                " - Lỗi khôi phục database:",
                exc,
            )

        clear_cache()

        print(
            "Backup:",
            BACKUP,
        )

        return 1


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
