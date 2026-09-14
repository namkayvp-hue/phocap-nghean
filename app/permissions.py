from __future__ import annotations

from typing import Any


LEGACY_ADMIN_ROLE_CODE = "SO"
ADMIN_ROLE_CODE = "ADMIN"
DEPARTMENT_ROLE_CODE = "PHONG_BAN"
COMMUNE_ROLE_CODE = "XA"
SCHOOL_ROLE_CODE = "TRUONG"
TEACHER_ROLE_CODE = "GIAO_VIEN"

# SO được giữ tạm thời để hệ thống cũ vẫn hoạt động trong giai đoạn chuyển đổi.
ADMIN_ROLE_CODES = frozenset({
    ADMIN_ROLE_CODE,
    LEGACY_ADMIN_ROLE_CODE,
})

PROVINCE_READ_ROLE_CODES = frozenset({
    ADMIN_ROLE_CODE,
    LEGACY_ADMIN_ROLE_CODE,
    DEPARTMENT_ROLE_CODE,
})

SURVEY_ROLE_CODES = frozenset({
    ADMIN_ROLE_CODE,
    LEGACY_ADMIN_ROLE_CODE,
    DEPARTMENT_ROLE_CODE,
    COMMUNE_ROLE_CODE,
    SCHOOL_ROLE_CODE,
    TEACHER_ROLE_CODE,
})

ACCOUNT_MANAGEMENT_ROLE_CODES = frozenset({
    ADMIN_ROLE_CODE,
    LEGACY_ADMIN_ROLE_CODE,
    SCHOOL_ROLE_CODE,
})

ASSIGNMENT_MANAGEMENT_ROLE_CODES = frozenset({
    ADMIN_ROLE_CODE,
    LEGACY_ADMIN_ROLE_CODE,
    COMMUNE_ROLE_CODE,
    SCHOOL_ROLE_CODE,
})

READ_ONLY_DATA_ROLE_CODES = frozenset({
    DEPARTMENT_ROLE_CODE,
    COMMUNE_ROLE_CODE,
    SCHOOL_ROLE_CODE,
})


def normalize_role_code(value: Any) -> str:
    return str(value or "").strip().upper()


def role_code_from_user(user: dict[str, Any] | None) -> str:
    return normalize_role_code((user or {}).get("role_code"))


def is_admin_role(role_code: Any) -> bool:
    return normalize_role_code(role_code) in ADMIN_ROLE_CODES


def is_province_reader(role_code: Any) -> bool:
    return normalize_role_code(role_code) in PROVINCE_READ_ROLE_CODES


def can_manage_accounts(role_code: Any) -> bool:
    return normalize_role_code(role_code) in ACCOUNT_MANAGEMENT_ROLE_CODES


def can_edit_survey_data(role_code: Any) -> bool:
    normalized = normalize_role_code(role_code)
    return normalized in ADMIN_ROLE_CODES or normalized == TEACHER_ROLE_CODE


def can_manage_survey_assignments(role_code: Any) -> bool:
    return normalize_role_code(role_code) in ASSIGNMENT_MANAGEMENT_ROLE_CODES
