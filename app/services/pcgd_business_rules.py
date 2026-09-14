from __future__ import annotations

"""
BÀI 13B-11.15.2.4.4
Bộ quy tắc nghiệp vụ dùng chung cho báo cáo PCGD/XMC.

Mục tiêu:
- Chuẩn hóa cách hiểu số liệu Tiểu học / THCS theo hướng dẫn nghiệp vụ 2025.
- Chuẩn hóa ngưỡng công nhận theo Nghị định 20/2014/NĐ-CP.
- Chuẩn hóa ngưỡng PCGDMN 3-5 tuổi theo Nghị định 277/2025/NĐ-CP.
- Không phụ thuộc Excel để quyết định Đạt/Không đạt.
- Không tự coi "vùng khó khăn" trong lộ trình là "đặc biệt khó khăn" theo pháp luật.

Nguồn pháp lý:
- Nghị định 20/2014/NĐ-CP ngày 24/03/2014.
- Nghị định 277/2025/NĐ-CP ngày 20/10/2025.

Nguồn nghiệp vụ người dùng cung cấp:
- Những hướng dẫn cơ bản về nhập số liệu trên các mẫu PCGD TH 2025.pdf
- Những hướng dẫn cơ bản về nhập số liệu trên các mẫu PCGD THCS 2025.pdf
- Lộ trình công nhận phổ cập.xlsx
"""

from dataclasses import dataclass
from typing import Any, Mapping


# ---------------------------------------------------------------------------
# 1. Helper chung
# ---------------------------------------------------------------------------

def safe_percent(numerator: float | int | None, denominator: float | int | None) -> float | None:
    if numerator is None or denominator is None:
        return None
    try:
        n = float(numerator)
        d = float(denominator)
    except (TypeError, ValueError):
        return None
    if d <= 0:
        return None
    return round(n * 100.0 / d, 2)


def safe_ratio(numerator: float | int | None, denominator: float | int | None) -> float | None:
    if numerator is None or denominator is None:
        return None
    try:
        n = float(numerator)
        d = float(denominator)
    except (TypeError, ValueError):
        return None
    if d <= 0:
        return None
    return round(n / d, 2)


def primary_ppc_count(
    total: int,
    disabled: int,
    move_out: int,
    deceased: int,
) -> int:
    """
    Hướng dẫn TH 2025:
    PPC = Tổng số - khuyết tật - chuyển đi - chết.
    Chuyển đến nằm trong Tổng số và không bị trừ ở công thức này.
    """
    return max(0, int(total or 0) - int(disabled or 0) - int(move_out or 0) - int(deceased or 0))


# ---------------------------------------------------------------------------
# 2. Quy ước phạm vi học tập theo hướng dẫn người dùng cung cấp
# ---------------------------------------------------------------------------

PRIMARY_LOCATION_SEMANTICS = {
    "TAI_CHO": "Có hộ khẩu tại xã, học tại trường Tiểu học trong xã.",
    "DI_HOC_NOI_KHAC": "Có hộ khẩu tại xã, học tại trường Tiểu học ngoài xã.",
    "NOI_KHAC_DEN": "Có hộ khẩu ngoài xã, đến học tại trường Tiểu học trong xã.",
}

LOWER_SECONDARY_LOCATION_SEMANTICS = {
    "TAI_CHO": "Có hộ khẩu tại xã, học/TN THCS tại trường THCS trong xã.",
    "DI_HOC_NOI_KHAC": "Có hộ khẩu tại xã, học/TN THCS tại trường THCS ngoài xã.",
    "NOI_KHAC_DEN": "Có hộ khẩu ngoài xã, đến học/TN THCS tại trường THCS trong xã.",
}

POST_LOWER_SECONDARY_LOCATION_SEMANTICS = {
    "TAI_CHO": "Có hộ khẩu tại xã, đã/đang học THPT, GDTX cấp THPT hoặc GDNN trong tỉnh.",
    "DI_HOC_NOI_KHAC": "Có hộ khẩu tại xã, đã/đang học THPT, GDTX cấp THPT hoặc GDNN ngoài tỉnh.",
}

CROSS_REPORT_CONSISTENCY = {
    "birth_year_2019": "Tổng số và PPC ở M1 Tiểu học phải thống nhất với M1 Mầm non.",
    "birth_year_2014": "Tổng số và PPC ở M1 Tiểu học phải thống nhất với M1 THCS.",
    "birth_years_2011_2014": "Tổng số và PPC các năm sinh 2011-2014 ở M1 Tiểu học/THCS phải thống nhất.",
}

STAFF_RATIO_RULES = {
    "TH": "Tổng số giáo viên Tiểu học toàn xã / tổng số lớp Tiểu học toàn xã.",
    "THCS": "Tổng số giáo viên THCS toàn xã / tổng số lớp THCS toàn xã.",
}

FACILITY_RULES = {
    "school_site": "Điểm trường = số điểm lẻ.",
}


# ---------------------------------------------------------------------------
# 3. Ngưỡng Nghị định 20/2014/NĐ-CP
# ---------------------------------------------------------------------------

PRIMARY_THRESHOLDS = {
    1: {
        "age6_grade1_rate": 90.0,
        "age14_completed_rate_normal": 80.0,
        "age14_completed_rate_special_difficult": 70.0,
    },
    2: {
        "age6_grade1_rate": 95.0,
        "age11_completed_rate_normal": 80.0,
        "age11_completed_rate_special_difficult": 70.0,
        "age11_remaining_must_all_study_primary": True,
    },
    3: {
        "age6_grade1_rate": 98.0,
        "age11_completed_rate_normal": 90.0,
        "age11_completed_rate_special_difficult": 80.0,
        "age11_remaining_must_all_study_primary": True,
    },
}

THCS_THRESHOLDS = {
    1: {
        "requires_primary_level": 1,
        "requires_literacy_level": 1,
        "age15_18_graduated_thcs_rate_normal": 80.0,
        "age15_18_graduated_thcs_rate_special_difficult": 70.0,
    },
    2: {
        "requires_thcs_level": 1,
        "age15_18_graduated_thcs_rate_normal": 90.0,
        "age15_18_graduated_thcs_rate_special_difficult": 80.0,
    },
    3: {
        "requires_thcs_level": 2,
        "age15_18_graduated_thcs_rate_normal": 95.0,
        "age15_18_graduated_thcs_rate_special_difficult": 90.0,
        "age15_18_upper_program_rate_normal": 80.0,
        "age15_18_upper_program_rate_special_difficult": 70.0,
    },
}

LITERACY_THRESHOLDS = {
    1: {
        "normal_age_range": "15-35",
        "special_difficult_age_range": "15-25",
        "minimum_rate": 90.0,
        "literacy_level": 1,
    },
    2: {
        "normal_age_range": "15-60",
        "special_difficult_age_range": "15-35",
        "minimum_rate": 90.0,
        "literacy_level": 2,
    },
}

LEGACY_PRESCHOOL_5_ND20 = {
    "attendance_rate_normal": 95.0,
    "attendance_rate_special_difficult": 90.0,
    "completion_rate_normal": 85.0,
    "completion_rate_special_difficult": 80.0,
}


# ---------------------------------------------------------------------------
# 4. Ngưỡng Nghị định 277/2025/NĐ-CP - PCGDMN trẻ 3-5 tuổi
# ---------------------------------------------------------------------------

PRESCHOOL_3_5_ND277 = {
    "attendance_rate_normal": 90.0,
    "attendance_rate_special_difficult": 85.0,
    "completion_rate_normal": 85.0,
    "completion_rate_special_difficult": 80.0,
    "province_recognition": {
        "special_difficult_communes_recognized_min_rate": 85.0,
        "other_communes_recognized_min_rate": 90.0,
    },
    "national_roadmap": {
        2028: "Ít nhất 50% tỉnh/thành phố đạt chuẩn.",
        2030: "100% tỉnh/thành phố đạt chuẩn.",
    },
}


# ---------------------------------------------------------------------------
# 5. Kết quả đánh giá
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RuleCheck:
    key: str
    actual: Any
    required: Any
    passed: bool | None
    note: str = ""


@dataclass(frozen=True)
class RecognitionResult:
    program: str
    level: int | None
    passed: bool
    checks: tuple[RuleCheck, ...]
    missing_fields: tuple[str, ...]


def _gte(actual: Any, required: float) -> bool | None:
    if actual is None:
        return None
    try:
        return float(actual) >= float(required)
    except (TypeError, ValueError):
        return None


def _required_rate(normal: float, difficult: float, is_special_difficult: bool) -> float:
    return difficult if is_special_difficult else normal


def _finalize(program: str, level: int | None, checks: list[RuleCheck], missing: list[str]) -> RecognitionResult:
    passed = bool(checks) and all(check.passed is True for check in checks) and not missing
    return RecognitionResult(
        program=program,
        level=level if passed else None,
        passed=passed,
        checks=tuple(checks),
        missing_fields=tuple(dict.fromkeys(missing)),
    )


def evaluate_primary_commune(
    metrics: Mapping[str, Any],
    *,
    is_special_difficult: bool,
) -> RecognitionResult:
    """
    metrics:
      age6_grade1_rate
      age14_completed_rate
      age11_completed_rate
      age11_remaining_all_study_primary
    """
    missing: list[str] = []

    def val(key: str) -> Any:
        value = metrics.get(key)
        if value is None:
            missing.append(key)
        return value

    age6 = val("age6_grade1_rate")
    age14 = val("age14_completed_rate")

    l1_age14_req = _required_rate(80.0, 70.0, is_special_difficult)
    l1 = [
        RuleCheck("age6_grade1_rate", age6, 90.0, _gte(age6, 90.0)),
        RuleCheck("age14_completed_rate", age14, l1_age14_req, _gte(age14, l1_age14_req)),
    ]
    if not missing and all(c.passed is True for c in l1):
        level = 1
    else:
        return _finalize("PRIMARY_ND20", 1, l1, missing)

    age11 = val("age11_completed_rate")
    remaining = val("age11_remaining_all_study_primary")
    l2_req = _required_rate(80.0, 70.0, is_special_difficult)
    l2 = l1 + [
        RuleCheck("age6_grade1_rate_L2", age6, 95.0, _gte(age6, 95.0)),
        RuleCheck("age11_completed_rate_L2", age11, l2_req, _gte(age11, l2_req)),
        RuleCheck("age11_remaining_all_study_primary_L2", remaining, True, remaining is True if remaining is not None else None),
    ]
    if not missing and all(c.passed is True for c in l2):
        level = 2
    else:
        return RecognitionResult("PRIMARY_ND20", level, True, tuple(l2), tuple(dict.fromkeys(missing)))

    l3_req = _required_rate(90.0, 80.0, is_special_difficult)
    l3 = l2 + [
        RuleCheck("age6_grade1_rate_L3", age6, 98.0, _gte(age6, 98.0)),
        RuleCheck("age11_completed_rate_L3", age11, l3_req, _gte(age11, l3_req)),
        RuleCheck("age11_remaining_all_study_primary_L3", remaining, True, remaining is True if remaining is not None else None),
    ]
    if not missing and all(c.passed is True for c in l3):
        return RecognitionResult("PRIMARY_ND20", 3, True, tuple(l3), ())
    return RecognitionResult("PRIMARY_ND20", level, True, tuple(l3), tuple(dict.fromkeys(missing)))


def evaluate_literacy_commune(
    metrics: Mapping[str, Any],
    *,
    is_special_difficult: bool,
) -> RecognitionResult:
    """
    metrics:
      literacy_level1_rate_15_25
      literacy_level1_rate_15_35
      literacy_level2_rate_15_35
      literacy_level2_rate_15_60
    """
    if is_special_difficult:
        l1_key = "literacy_level1_rate_15_25"
        l2_key = "literacy_level2_rate_15_35"
    else:
        l1_key = "literacy_level1_rate_15_35"
        l2_key = "literacy_level2_rate_15_60"

    missing = []
    l1_rate = metrics.get(l1_key)
    if l1_rate is None:
        missing.append(l1_key)

    l1_check = RuleCheck(l1_key, l1_rate, 90.0, _gte(l1_rate, 90.0))
    if missing or l1_check.passed is not True:
        return _finalize("LITERACY_ND20", 1, [l1_check], missing)

    l2_rate = metrics.get(l2_key)
    if l2_rate is None:
        missing.append(l2_key)

    l2_check = RuleCheck(l2_key, l2_rate, 90.0, _gte(l2_rate, 90.0))
    if not missing and l2_check.passed is True:
        return RecognitionResult("LITERACY_ND20", 2, True, (l1_check, l2_check), ())
    return RecognitionResult("LITERACY_ND20", 1, True, (l1_check, l2_check), tuple(dict.fromkeys(missing)))


def evaluate_thcs_commune(
    metrics: Mapping[str, Any],
    *,
    primary_level: int | None,
    literacy_level: int | None,
    is_special_difficult: bool,
) -> RecognitionResult:
    """
    metrics:
      age15_18_graduated_thcs_rate
      age15_18_upper_program_rate
    """
    missing = []
    grad = metrics.get("age15_18_graduated_thcs_rate")
    if grad is None:
        missing.append("age15_18_graduated_thcs_rate")

    l1_req = _required_rate(80.0, 70.0, is_special_difficult)
    checks = [
        RuleCheck("primary_level", primary_level, ">=1", (primary_level or 0) >= 1 if primary_level is not None else None),
        RuleCheck("literacy_level", literacy_level, ">=1", (literacy_level or 0) >= 1 if literacy_level is not None else None),
        RuleCheck("age15_18_graduated_thcs_rate_L1", grad, l1_req, _gte(grad, l1_req)),
    ]
    if primary_level is None:
        missing.append("primary_level")
    if literacy_level is None:
        missing.append("literacy_level")

    if missing or not all(c.passed is True for c in checks):
        return _finalize("THCS_ND20", 1, checks, missing)

    level = 1
    l2_req = _required_rate(90.0, 80.0, is_special_difficult)
    l2_check = RuleCheck("age15_18_graduated_thcs_rate_L2", grad, l2_req, _gte(grad, l2_req))
    checks.append(l2_check)

    if l2_check.passed is not True:
        return RecognitionResult("THCS_ND20", level, True, tuple(checks), ())

    level = 2
    upper = metrics.get("age15_18_upper_program_rate")
    if upper is None:
        missing.append("age15_18_upper_program_rate")

    l3_grad_req = _required_rate(95.0, 90.0, is_special_difficult)
    l3_upper_req = _required_rate(80.0, 70.0, is_special_difficult)

    checks.extend([
        RuleCheck("age15_18_graduated_thcs_rate_L3", grad, l3_grad_req, _gte(grad, l3_grad_req)),
        RuleCheck("age15_18_upper_program_rate_L3", upper, l3_upper_req, _gte(upper, l3_upper_req)),
    ])

    if not missing and all(c.passed is True for c in checks):
        return RecognitionResult("THCS_ND20", 3, True, tuple(checks), ())
    return RecognitionResult("THCS_ND20", level, True, tuple(checks), tuple(dict.fromkeys(missing)))


def evaluate_preschool_3_5_commune(
    metrics: Mapping[str, Any],
    *,
    is_special_difficult: bool,
) -> RecognitionResult:
    """
    metrics:
      attendance_rate_3_5
      completion_rate_3_5_by_age:
        - có thể là một số %, hoặc
        - dict {3: %, 4: %, 5: %}; nếu là dict thì yêu cầu đủ cả 3 tuổi.
    """
    attendance = metrics.get("attendance_rate_3_5")
    completion = metrics.get("completion_rate_3_5_by_age")

    attendance_req = _required_rate(90.0, 85.0, is_special_difficult)
    completion_req = _required_rate(85.0, 80.0, is_special_difficult)

    checks: list[RuleCheck] = []
    missing: list[str] = []

    if attendance is None:
        missing.append("attendance_rate_3_5")
    checks.append(
        RuleCheck(
            "attendance_rate_3_5",
            attendance,
            attendance_req,
            _gte(attendance, attendance_req),
        )
    )

    if isinstance(completion, Mapping):
        for age in (3, 4, 5):
            value = completion.get(age, completion.get(str(age)))
            if value is None:
                missing.append(f"completion_rate_age_{age}")
            checks.append(
                RuleCheck(
                    f"completion_rate_age_{age}",
                    value,
                    completion_req,
                    _gte(value, completion_req),
                    "NĐ277: hoàn thành Chương trình GDMN theo độ tuổi hằng năm.",
                )
            )
    else:
        if completion is None:
            missing.append("completion_rate_3_5_by_age")
        checks.append(
            RuleCheck(
                "completion_rate_3_5_by_age",
                completion,
                completion_req,
                _gte(completion, completion_req),
            )
        )

    return _finalize("PRESCHOOL_3_5_ND277", 1, checks, missing)

# === BAI_13B_11_15_2_4_9_2_PROVINCE_RULES_START ===
# Bài 13B-11.15.2.4.9.2 - quy tắc công nhận cấp tỉnh.
# Cấp tỉnh đánh giá từng xã/phường rồi tổng hợp tỷ lệ, không dùng
# dữ liệu toàn tỉnh làm đầu vào trực tiếp cho evaluator cấp xã.

PROVINCE_RECOGNITION_ND142_2025 = {
    "primary": {1: 90.0, 2: 90.0, 3: 90.0},
    "thcs": {1: 90.0, 2: 95.0, 3: 100.0},
    "literacy": {1: 81.0, 2: 90.0},
}


def _b492_bool_status(value):
    if value is True or value == 1:
        return True
    if value is False or value == 0:
        return False
    return None


def _b492_group_check(*, key: str, statuses, required: float):
    values = [_b492_bool_status(v) for v in list(statuses or ())]
    total = len(values)

    if total <= 0:
        return (
            RuleCheck(key, None, float(required), None, "Không có đơn vị cấp xã."),
            True,
        )

    recognized = sum(1 for v in values if v is True)
    unknown = sum(1 for v in values if v is None)

    min_rate = recognized * 100.0 / total
    max_rate = (recognized + unknown) * 100.0 / total

    if min_rate >= float(required):
        passed = True
        uncertain = False
    elif max_rate < float(required):
        passed = False
        uncertain = False
    else:
        passed = None
        uncertain = True

    note = (
        f"Đạt chắc chắn={recognized}/{total}; chưa đủ dữ liệu={unknown}; "
        f"khoảng tỷ lệ={min_rate:.2f}%..{max_rate:.2f}%."
    )

    return (
        RuleCheck(key, round(min_rate, 6), float(required), passed, note),
        uncertain,
    )


def evaluate_preschool_3_5_province(
    *,
    special_difficult_commune_statuses,
    other_commune_statuses,
) -> RecognitionResult:
    special_required = float(
        PRESCHOOL_3_5_ND277["province_recognition"][
            "special_difficult_communes_recognized_min_rate"
        ]
    )
    other_required = float(
        PRESCHOOL_3_5_ND277["province_recognition"][
            "other_communes_recognized_min_rate"
        ]
    )

    special_check, special_uncertain = _b492_group_check(
        key="special_difficult_communes_recognized_rate",
        statuses=special_difficult_commune_statuses,
        required=special_required,
    )
    other_check, other_uncertain = _b492_group_check(
        key="other_communes_recognized_rate",
        statuses=other_commune_statuses,
        required=other_required,
    )

    checks = (special_check, other_check)
    definitive_fail = any(c.passed is False for c in checks)

    if definitive_fail:
        return RecognitionResult(
            program="PRESCHOOL_3_5_ND277_PROVINCE",
            level=None,
            passed=False,
            checks=checks,
            missing_fields=(),
        )

    missing = []
    if special_uncertain:
        missing.append("special_difficult_communes_status")
    if other_uncertain:
        missing.append("other_communes_status")

    passed = all(c.passed is True for c in checks) and not missing

    return RecognitionResult(
        program="PRESCHOOL_3_5_ND277_PROVINCE",
        level=1 if passed else None,
        passed=passed,
        checks=checks,
        missing_fields=tuple(missing),
    )


def _b492_normalize_level_item(item):
    if isinstance(item, dict):
        raw_level = item.get("level")
        incomplete = bool(item.get("incomplete") or item.get("missing"))
    elif isinstance(item, (tuple, list)) and len(item) >= 2:
        raw_level = item[0]
        incomplete = bool(item[1])
    else:
        raw_level = item
        incomplete = item is None

    if raw_level is None:
        return None, bool(incomplete)

    try:
        level = int(raw_level)
    except (TypeError, ValueError):
        return None, True

    if level < 0:
        return None, True

    return level, bool(incomplete)


def _b492_level_check(*, items, target_level: int, required: float, key: str):
    normalized = [_b492_normalize_level_item(item) for item in list(items or ())]
    total = len(normalized)

    if total <= 0:
        return (
            RuleCheck(key, None, float(required), None, "Không có đơn vị cấp xã."),
            True,
        )

    recognized = 0
    unknown = 0

    for confirmed_level, incomplete in normalized:
        if confirmed_level is None:
            unknown += 1
        elif confirmed_level >= int(target_level):
            recognized += 1
        elif incomplete:
            unknown += 1

    min_rate = recognized * 100.0 / total
    max_rate = (recognized + unknown) * 100.0 / total

    if min_rate >= float(required):
        passed = True
        uncertain = False
    elif max_rate < float(required):
        passed = False
        uncertain = False
    else:
        passed = None
        uncertain = True

    note = (
        f"Đạt chắc chắn M{target_level}+={recognized}/{total}; "
        f"chưa xác định={unknown}; khoảng tỷ lệ={min_rate:.2f}%..{max_rate:.2f}%."
    )

    return (
        RuleCheck(key, round(min_rate, 6), float(required), passed, note),
        uncertain,
    )


def _b492_evaluate_level_province(*, program: str, commune_levels, thresholds):
    items = list(commune_levels or ())
    checks = []
    confirmed_level = None

    for target_level in sorted(int(x) for x in thresholds):
        check, uncertain = _b492_level_check(
            items=items,
            target_level=target_level,
            required=float(thresholds[target_level]),
            key=f"communes_recognized_level_{target_level}_rate",
        )
        checks.append(check)

        if check.passed is True:
            confirmed_level = target_level
            continue

        if uncertain:
            missing = (f"commune_levels_L{target_level}",)
            if confirmed_level is not None:
                return RecognitionResult(
                    program=program,
                    level=confirmed_level,
                    passed=True,
                    checks=tuple(checks),
                    missing_fields=missing,
                )
            return RecognitionResult(
                program=program,
                level=None,
                passed=False,
                checks=tuple(checks),
                missing_fields=missing,
            )

        if confirmed_level is not None:
            return RecognitionResult(
                program=program,
                level=confirmed_level,
                passed=True,
                checks=tuple(checks),
                missing_fields=(),
            )

        return RecognitionResult(
            program=program,
            level=None,
            passed=False,
            checks=tuple(checks),
            missing_fields=(),
        )

    if confirmed_level is not None:
        return RecognitionResult(
            program=program,
            level=confirmed_level,
            passed=True,
            checks=tuple(checks),
            missing_fields=(),
        )

    return RecognitionResult(
        program=program,
        level=None,
        passed=False,
        checks=tuple(checks),
        missing_fields=(),
    )


def evaluate_primary_province(commune_levels) -> RecognitionResult:
    return _b492_evaluate_level_province(
        program="PRIMARY_ND20_ND142_PROVINCE",
        commune_levels=commune_levels,
        thresholds=PROVINCE_RECOGNITION_ND142_2025["primary"],
    )


def evaluate_literacy_province(commune_levels) -> RecognitionResult:
    return _b492_evaluate_level_province(
        program="LITERACY_ND20_ND142_PROVINCE",
        commune_levels=commune_levels,
        thresholds=PROVINCE_RECOGNITION_ND142_2025["literacy"],
    )


def evaluate_thcs_province(commune_levels) -> RecognitionResult:
    return _b492_evaluate_level_province(
        program="THCS_ND20_ND142_PROVINCE",
        commune_levels=commune_levels,
        thresholds=PROVINCE_RECOGNITION_ND142_2025["thcs"],
    )
# === BAI_13B_11_15_2_4_9_2_PROVINCE_RULES_END ===
