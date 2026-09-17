from __future__ import annotations

import ast
import json
import os
import shutil
import sqlite3
import unicodedata
from datetime import datetime
from pathlib import Path


PROJECT = Path(os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")).resolve()
APP = PROJECT / "app"
SERVICES = APP / "services"
DATA_DIR = APP / "data"
EXPORTS = PROJECT / "exports"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP_DIR = EXPORTS / f"backup_bai_13b_11_15_2_4_4_{STAMP}"

SERVICE_FILE = SERVICES / "pcgd_business_rules.py"
ROADMAP_FILE = DATA_DIR / "pcgd_recognition_roadmap_2026_2030.json"
REPORT_FILE = EXPORTS / f"bao_cao_bai_13b_11_15_2_4_4_{STAMP}.txt"

SERVICE_CONTENT = 'from __future__ import annotations\n\n"""\nBÀI 13B-11.15.2.4.4\nBộ quy tắc nghiệp vụ dùng chung cho báo cáo PCGD/XMC.\n\nMục tiêu:\n- Chuẩn hóa cách hiểu số liệu Tiểu học / THCS theo hướng dẫn nghiệp vụ 2025.\n- Chuẩn hóa ngưỡng công nhận theo Nghị định 20/2014/NĐ-CP.\n- Chuẩn hóa ngưỡng PCGDMN 3-5 tuổi theo Nghị định 277/2025/NĐ-CP.\n- Không phụ thuộc Excel để quyết định Đạt/Không đạt.\n- Không tự coi "vùng khó khăn" trong lộ trình là "đặc biệt khó khăn" theo pháp luật.\n\nNguồn pháp lý:\n- Nghị định 20/2014/NĐ-CP ngày 24/03/2014.\n- Nghị định 277/2025/NĐ-CP ngày 20/10/2025.\n\nNguồn nghiệp vụ người dùng cung cấp:\n- Những hướng dẫn cơ bản về nhập số liệu trên các mẫu PCGD TH 2025.pdf\n- Những hướng dẫn cơ bản về nhập số liệu trên các mẫu PCGD THCS 2025.pdf\n- Lộ trình công nhận phổ cập.xlsx\n"""\n\nfrom dataclasses import dataclass\nfrom typing import Any, Mapping\n\n\n# ---------------------------------------------------------------------------\n# 1. Helper chung\n# ---------------------------------------------------------------------------\n\ndef safe_percent(numerator: float | int | None, denominator: float | int | None) -> float | None:\n    if numerator is None or denominator is None:\n        return None\n    try:\n        n = float(numerator)\n        d = float(denominator)\n    except (TypeError, ValueError):\n        return None\n    if d <= 0:\n        return None\n    return round(n * 100.0 / d, 2)\n\n\ndef safe_ratio(numerator: float | int | None, denominator: float | int | None) -> float | None:\n    if numerator is None or denominator is None:\n        return None\n    try:\n        n = float(numerator)\n        d = float(denominator)\n    except (TypeError, ValueError):\n        return None\n    if d <= 0:\n        return None\n    return round(n / d, 2)\n\n\ndef primary_ppc_count(\n    total: int,\n    disabled: int,\n    move_out: int,\n    deceased: int,\n) -> int:\n    """\n    Hướng dẫn TH 2025:\n    PPC = Tổng số - khuyết tật - chuyển đi - chết.\n    Chuyển đến nằm trong Tổng số và không bị trừ ở công thức này.\n    """\n    return max(0, int(total or 0) - int(disabled or 0) - int(move_out or 0) - int(deceased or 0))\n\n\n# ---------------------------------------------------------------------------\n# 2. Quy ước phạm vi học tập theo hướng dẫn người dùng cung cấp\n# ---------------------------------------------------------------------------\n\nPRIMARY_LOCATION_SEMANTICS = {\n    "TAI_CHO": "Có hộ khẩu tại xã, học tại trường Tiểu học trong xã.",\n    "DI_HOC_NOI_KHAC": "Có hộ khẩu tại xã, học tại trường Tiểu học ngoài xã.",\n    "NOI_KHAC_DEN": "Có hộ khẩu ngoài xã, đến học tại trường Tiểu học trong xã.",\n}\n\nLOWER_SECONDARY_LOCATION_SEMANTICS = {\n    "TAI_CHO": "Có hộ khẩu tại xã, học/TN THCS tại trường THCS trong xã.",\n    "DI_HOC_NOI_KHAC": "Có hộ khẩu tại xã, học/TN THCS tại trường THCS ngoài xã.",\n    "NOI_KHAC_DEN": "Có hộ khẩu ngoài xã, đến học/TN THCS tại trường THCS trong xã.",\n}\n\nPOST_LOWER_SECONDARY_LOCATION_SEMANTICS = {\n    "TAI_CHO": "Có hộ khẩu tại xã, đã/đang học THPT, GDTX cấp THPT hoặc GDNN trong tỉnh.",\n    "DI_HOC_NOI_KHAC": "Có hộ khẩu tại xã, đã/đang học THPT, GDTX cấp THPT hoặc GDNN ngoài tỉnh.",\n}\n\nCROSS_REPORT_CONSISTENCY = {\n    "birth_year_2019": "Tổng số và PPC ở M1 Tiểu học phải thống nhất với M1 Mầm non.",\n    "birth_year_2014": "Tổng số và PPC ở M1 Tiểu học phải thống nhất với M1 THCS.",\n    "birth_years_2011_2014": "Tổng số và PPC các năm sinh 2011-2014 ở M1 Tiểu học/THCS phải thống nhất.",\n}\n\nSTAFF_RATIO_RULES = {\n    "TH": "Tổng số giáo viên Tiểu học toàn xã / tổng số lớp Tiểu học toàn xã.",\n    "THCS": "Tổng số giáo viên THCS toàn xã / tổng số lớp THCS toàn xã.",\n}\n\nFACILITY_RULES = {\n    "school_site": "Điểm trường = số điểm lẻ.",\n}\n\n\n# ---------------------------------------------------------------------------\n# 3. Ngưỡng Nghị định 20/2014/NĐ-CP\n# ---------------------------------------------------------------------------\n\nPRIMARY_THRESHOLDS = {\n    1: {\n        "age6_grade1_rate": 90.0,\n        "age14_completed_rate_normal": 80.0,\n        "age14_completed_rate_special_difficult": 70.0,\n    },\n    2: {\n        "age6_grade1_rate": 95.0,\n        "age11_completed_rate_normal": 80.0,\n        "age11_completed_rate_special_difficult": 70.0,\n        "age11_remaining_must_all_study_primary": True,\n    },\n    3: {\n        "age6_grade1_rate": 98.0,\n        "age11_completed_rate_normal": 90.0,\n        "age11_completed_rate_special_difficult": 80.0,\n        "age11_remaining_must_all_study_primary": True,\n    },\n}\n\nTHCS_THRESHOLDS = {\n    1: {\n        "requires_primary_level": 1,\n        "requires_literacy_level": 1,\n        "age15_18_graduated_thcs_rate_normal": 80.0,\n        "age15_18_graduated_thcs_rate_special_difficult": 70.0,\n    },\n    2: {\n        "requires_thcs_level": 1,\n        "age15_18_graduated_thcs_rate_normal": 90.0,\n        "age15_18_graduated_thcs_rate_special_difficult": 80.0,\n    },\n    3: {\n        "requires_thcs_level": 2,\n        "age15_18_graduated_thcs_rate_normal": 95.0,\n        "age15_18_graduated_thcs_rate_special_difficult": 90.0,\n        "age15_18_upper_program_rate_normal": 80.0,\n        "age15_18_upper_program_rate_special_difficult": 70.0,\n    },\n}\n\nLITERACY_THRESHOLDS = {\n    1: {\n        "normal_age_range": "15-35",\n        "special_difficult_age_range": "15-25",\n        "minimum_rate": 90.0,\n        "literacy_level": 1,\n    },\n    2: {\n        "normal_age_range": "15-60",\n        "special_difficult_age_range": "15-35",\n        "minimum_rate": 90.0,\n        "literacy_level": 2,\n    },\n}\n\nLEGACY_PRESCHOOL_5_ND20 = {\n    "attendance_rate_normal": 95.0,\n    "attendance_rate_special_difficult": 90.0,\n    "completion_rate_normal": 85.0,\n    "completion_rate_special_difficult": 80.0,\n}\n\n\n# ---------------------------------------------------------------------------\n# 4. Ngưỡng Nghị định 277/2025/NĐ-CP - PCGDMN trẻ 3-5 tuổi\n# ---------------------------------------------------------------------------\n\nPRESCHOOL_3_5_ND277 = {\n    "attendance_rate_normal": 90.0,\n    "attendance_rate_special_difficult": 85.0,\n    "completion_rate_normal": 85.0,\n    "completion_rate_special_difficult": 80.0,\n    "province_recognition": {\n        "special_difficult_communes_recognized_min_rate": 85.0,\n        "other_communes_recognized_min_rate": 90.0,\n    },\n    "national_roadmap": {\n        2028: "Ít nhất 50% tỉnh/thành phố đạt chuẩn.",\n        2030: "100% tỉnh/thành phố đạt chuẩn.",\n    },\n}\n\n\n# ---------------------------------------------------------------------------\n# 5. Kết quả đánh giá\n# ---------------------------------------------------------------------------\n\n@dataclass(frozen=True)\nclass RuleCheck:\n    key: str\n    actual: Any\n    required: Any\n    passed: bool | None\n    note: str = ""\n\n\n@dataclass(frozen=True)\nclass RecognitionResult:\n    program: str\n    level: int | None\n    passed: bool\n    checks: tuple[RuleCheck, ...]\n    missing_fields: tuple[str, ...]\n\n\ndef _gte(actual: Any, required: float) -> bool | None:\n    if actual is None:\n        return None\n    try:\n        return float(actual) >= float(required)\n    except (TypeError, ValueError):\n        return None\n\n\ndef _required_rate(normal: float, difficult: float, is_special_difficult: bool) -> float:\n    return difficult if is_special_difficult else normal\n\n\ndef _finalize(program: str, level: int | None, checks: list[RuleCheck], missing: list[str]) -> RecognitionResult:\n    passed = bool(checks) and all(check.passed is True for check in checks) and not missing\n    return RecognitionResult(\n        program=program,\n        level=level if passed else None,\n        passed=passed,\n        checks=tuple(checks),\n        missing_fields=tuple(dict.fromkeys(missing)),\n    )\n\n\ndef evaluate_primary_commune(\n    metrics: Mapping[str, Any],\n    *,\n    is_special_difficult: bool,\n) -> RecognitionResult:\n    """\n    metrics:\n      age6_grade1_rate\n      age14_completed_rate\n      age11_completed_rate\n      age11_remaining_all_study_primary\n    """\n    missing: list[str] = []\n\n    def val(key: str) -> Any:\n        value = metrics.get(key)\n        if value is None:\n            missing.append(key)\n        return value\n\n    age6 = val("age6_grade1_rate")\n    age14 = val("age14_completed_rate")\n\n    l1_age14_req = _required_rate(80.0, 70.0, is_special_difficult)\n    l1 = [\n        RuleCheck("age6_grade1_rate", age6, 90.0, _gte(age6, 90.0)),\n        RuleCheck("age14_completed_rate", age14, l1_age14_req, _gte(age14, l1_age14_req)),\n    ]\n    if not missing and all(c.passed is True for c in l1):\n        level = 1\n    else:\n        return _finalize("PRIMARY_ND20", 1, l1, missing)\n\n    age11 = val("age11_completed_rate")\n    remaining = val("age11_remaining_all_study_primary")\n    l2_req = _required_rate(80.0, 70.0, is_special_difficult)\n    l2 = l1 + [\n        RuleCheck("age6_grade1_rate_L2", age6, 95.0, _gte(age6, 95.0)),\n        RuleCheck("age11_completed_rate_L2", age11, l2_req, _gte(age11, l2_req)),\n        RuleCheck("age11_remaining_all_study_primary_L2", remaining, True, remaining is True if remaining is not None else None),\n    ]\n    if not missing and all(c.passed is True for c in l2):\n        level = 2\n    else:\n        return RecognitionResult("PRIMARY_ND20", level, True, tuple(l2), tuple(dict.fromkeys(missing)))\n\n    l3_req = _required_rate(90.0, 80.0, is_special_difficult)\n    l3 = l2 + [\n        RuleCheck("age6_grade1_rate_L3", age6, 98.0, _gte(age6, 98.0)),\n        RuleCheck("age11_completed_rate_L3", age11, l3_req, _gte(age11, l3_req)),\n        RuleCheck("age11_remaining_all_study_primary_L3", remaining, True, remaining is True if remaining is not None else None),\n    ]\n    if not missing and all(c.passed is True for c in l3):\n        return RecognitionResult("PRIMARY_ND20", 3, True, tuple(l3), ())\n    return RecognitionResult("PRIMARY_ND20", level, True, tuple(l3), tuple(dict.fromkeys(missing)))\n\n\ndef evaluate_literacy_commune(\n    metrics: Mapping[str, Any],\n    *,\n    is_special_difficult: bool,\n) -> RecognitionResult:\n    """\n    metrics:\n      literacy_level1_rate_15_25\n      literacy_level1_rate_15_35\n      literacy_level2_rate_15_35\n      literacy_level2_rate_15_60\n    """\n    if is_special_difficult:\n        l1_key = "literacy_level1_rate_15_25"\n        l2_key = "literacy_level2_rate_15_35"\n    else:\n        l1_key = "literacy_level1_rate_15_35"\n        l2_key = "literacy_level2_rate_15_60"\n\n    missing = []\n    l1_rate = metrics.get(l1_key)\n    if l1_rate is None:\n        missing.append(l1_key)\n\n    l1_check = RuleCheck(l1_key, l1_rate, 90.0, _gte(l1_rate, 90.0))\n    if missing or l1_check.passed is not True:\n        return _finalize("LITERACY_ND20", 1, [l1_check], missing)\n\n    l2_rate = metrics.get(l2_key)\n    if l2_rate is None:\n        missing.append(l2_key)\n\n    l2_check = RuleCheck(l2_key, l2_rate, 90.0, _gte(l2_rate, 90.0))\n    if not missing and l2_check.passed is True:\n        return RecognitionResult("LITERACY_ND20", 2, True, (l1_check, l2_check), ())\n    return RecognitionResult("LITERACY_ND20", 1, True, (l1_check, l2_check), tuple(dict.fromkeys(missing)))\n\n\ndef evaluate_thcs_commune(\n    metrics: Mapping[str, Any],\n    *,\n    primary_level: int | None,\n    literacy_level: int | None,\n    is_special_difficult: bool,\n) -> RecognitionResult:\n    """\n    metrics:\n      age15_18_graduated_thcs_rate\n      age15_18_upper_program_rate\n    """\n    missing = []\n    grad = metrics.get("age15_18_graduated_thcs_rate")\n    if grad is None:\n        missing.append("age15_18_graduated_thcs_rate")\n\n    l1_req = _required_rate(80.0, 70.0, is_special_difficult)\n    checks = [\n        RuleCheck("primary_level", primary_level, ">=1", (primary_level or 0) >= 1 if primary_level is not None else None),\n        RuleCheck("literacy_level", literacy_level, ">=1", (literacy_level or 0) >= 1 if literacy_level is not None else None),\n        RuleCheck("age15_18_graduated_thcs_rate_L1", grad, l1_req, _gte(grad, l1_req)),\n    ]\n    if primary_level is None:\n        missing.append("primary_level")\n    if literacy_level is None:\n        missing.append("literacy_level")\n\n    if missing or not all(c.passed is True for c in checks):\n        return _finalize("THCS_ND20", 1, checks, missing)\n\n    level = 1\n    l2_req = _required_rate(90.0, 80.0, is_special_difficult)\n    l2_check = RuleCheck("age15_18_graduated_thcs_rate_L2", grad, l2_req, _gte(grad, l2_req))\n    checks.append(l2_check)\n\n    if l2_check.passed is not True:\n        return RecognitionResult("THCS_ND20", level, True, tuple(checks), ())\n\n    level = 2\n    upper = metrics.get("age15_18_upper_program_rate")\n    if upper is None:\n        missing.append("age15_18_upper_program_rate")\n\n    l3_grad_req = _required_rate(95.0, 90.0, is_special_difficult)\n    l3_upper_req = _required_rate(80.0, 70.0, is_special_difficult)\n\n    checks.extend([\n        RuleCheck("age15_18_graduated_thcs_rate_L3", grad, l3_grad_req, _gte(grad, l3_grad_req)),\n        RuleCheck("age15_18_upper_program_rate_L3", upper, l3_upper_req, _gte(upper, l3_upper_req)),\n    ])\n\n    if not missing and all(c.passed is True for c in checks):\n        return RecognitionResult("THCS_ND20", 3, True, tuple(checks), ())\n    return RecognitionResult("THCS_ND20", level, True, tuple(checks), tuple(dict.fromkeys(missing)))\n\n\ndef evaluate_preschool_3_5_commune(\n    metrics: Mapping[str, Any],\n    *,\n    is_special_difficult: bool,\n) -> RecognitionResult:\n    """\n    metrics:\n      attendance_rate_3_5\n      completion_rate_3_5_by_age:\n        - có thể là một số %, hoặc\n        - dict {3: %, 4: %, 5: %}; nếu là dict thì yêu cầu đủ cả 3 tuổi.\n    """\n    attendance = metrics.get("attendance_rate_3_5")\n    completion = metrics.get("completion_rate_3_5_by_age")\n\n    attendance_req = _required_rate(90.0, 85.0, is_special_difficult)\n    completion_req = _required_rate(85.0, 80.0, is_special_difficult)\n\n    checks: list[RuleCheck] = []\n    missing: list[str] = []\n\n    if attendance is None:\n        missing.append("attendance_rate_3_5")\n    checks.append(\n        RuleCheck(\n            "attendance_rate_3_5",\n            attendance,\n            attendance_req,\n            _gte(attendance, attendance_req),\n        )\n    )\n\n    if isinstance(completion, Mapping):\n        for age in (3, 4, 5):\n            value = completion.get(age, completion.get(str(age)))\n            if value is None:\n                missing.append(f"completion_rate_age_{age}")\n            checks.append(\n                RuleCheck(\n                    f"completion_rate_age_{age}",\n                    value,\n                    completion_req,\n                    _gte(value, completion_req),\n                    "NĐ277: hoàn thành Chương trình GDMN theo độ tuổi hằng năm.",\n                )\n            )\n    else:\n        if completion is None:\n            missing.append("completion_rate_3_5_by_age")\n        checks.append(\n            RuleCheck(\n                "completion_rate_3_5_by_age",\n                completion,\n                completion_req,\n                _gte(completion, completion_req),\n            )\n        )\n\n    return _finalize("PRESCHOOL_3_5_ND277", 1, checks, missing)\n'

ROADMAP_RECORDS = [
  {
    "target_year": 2026,
    "order": 1,
    "commune_name": "Phường Thành Vinh",
    "is_difficult_area_from_roadmap": false
  },
  {
    "target_year": 2026,
    "order": 2,
    "commune_name": "Phường Trường Vinh",
    "is_difficult_area_from_roadmap": false
  },
  {
    "target_year": 2026,
    "order": 3,
    "commune_name": "Phường Vinh Phú",
    "is_difficult_area_from_roadmap": false
  },
  {
    "target_year": 2026,
    "order": 4,
    "commune_name": "Xã Hải Lộc",
    "is_difficult_area_from_roadmap": false
  },
  {
    "target_year": 2026,
    "order": 5,
    "commune_name": "Xã Hùng Chân",
    "is_difficult_area_from_roadmap": true
  },
  {
    "target_year": 2026,
    "order": 6,
    "commune_name": "Xã Nghi Lộc",
    "is_difficult_area_from_roadmap": false
  },
  {
    "target_year": 2026,
    "order": 7,
    "commune_name": "Xã Nhân Hòa",
    "is_difficult_area_from_roadmap": true
  },
  {
    "target_year": 2026,
    "order": 8,
    "commune_name": "Xã Phúc Lộc",
    "is_difficult_area_from_roadmap": false
  },
  {
    "target_year": 2026,
    "order": 9,
    "commune_name": "Xã Quỳnh Phú",
    "is_difficult_area_from_roadmap": false
  },
  {
    "target_year": 2026,
    "order": 10,
    "commune_name": "Xã Tân An",
    "is_difficult_area_from_roadmap": true
  },
  {
    "target_year": 2026,
    "order": 11,
    "commune_name": "Xã Tân Châu",
    "is_difficult_area_from_roadmap": false
  },
  {
    "target_year": 2026,
    "order": 12,
    "commune_name": "Xã Tiên Đồng",
    "is_difficult_area_from_roadmap": true
  },
  {
    "target_year": 2026,
    "order": 13,
    "commune_name": "Xã Trung Lộc",
    "is_difficult_area_from_roadmap": false
  },
  {
    "target_year": 2026,
    "order": 14,
    "commune_name": "Xã Tương Dương",
    "is_difficult_area_from_roadmap": true
  },
  {
    "target_year": 2026,
    "order": 15,
    "commune_name": "Xã Văn Hiến",
    "is_difficult_area_from_roadmap": false
  },
  {
    "target_year": 2027,
    "order": 1,
    "commune_name": "Phường Tây Hiếu",
    "is_difficult_area_from_roadmap": true
  },
  {
    "target_year": 2027,
    "order": 2,
    "commune_name": "Phường Thái Hòa",
    "is_difficult_area_from_roadmap": true
  },
  {
    "target_year": 2027,
    "order": 3,
    "commune_name": "Phường Vinh Hưng",
    "is_difficult_area_from_roadmap": false
  },
  {
    "target_year": 2027,
    "order": 4,
    "commune_name": "Phường Vinh Lộc",
    "is_difficult_area_from_roadmap": false
  },
  {
    "target_year": 2027,
    "order": 5,
    "commune_name": "Xã Anh Sơn",
    "is_difficult_area_from_roadmap": true
  },
  {
    "target_year": 2027,
    "order": 6,
    "commune_name": "Xã Bạch Hà",
    "is_difficult_area_from_roadmap": false
  },
  {
    "target_year": 2027,
    "order": 7,
    "commune_name": "Xã Bình Minh",
    "is_difficult_area_from_roadmap": false
  },
  {
    "target_year": 2027,
    "order": 8,
    "commune_name": "Xã Cam Phục",
    "is_difficult_area_from_roadmap": true
  },
  {
    "target_year": 2027,
    "order": 9,
    "commune_name": "Xã Diễn Châu",
    "is_difficult_area_from_roadmap": false
  },
  {
    "target_year": 2027,
    "order": 10,
    "commune_name": "Xã Đông Hiếu",
    "is_difficult_area_from_roadmap": true
  },
  {
    "target_year": 2027,
    "order": 11,
    "commune_name": "Xã Đông Lộc",
    "is_difficult_area_from_roadmap": false
  },
  {
    "target_year": 2027,
    "order": 12,
    "commune_name": "Xã Đức Châu",
    "is_difficult_area_from_roadmap": false
  },
  {
    "target_year": 2027,
    "order": 13,
    "commune_name": "Xã Hải Châu",
    "is_difficult_area_from_roadmap": false
  },
  {
    "target_year": 2027,
    "order": 14,
    "commune_name": "Xã Kim Liên",
    "is_difficult_area_from_roadmap": false
  },
  {
    "target_year": 2027,
    "order": 15,
    "commune_name": "Xã Mậu Thạch",
    "is_difficult_area_from_roadmap": true
  },
  {
    "target_year": 2027,
    "order": 16,
    "commune_name": "Xã Nghĩa Đồng",
    "is_difficult_area_from_roadmap": true
  },
  {
    "target_year": 2027,
    "order": 17,
    "commune_name": "Xã Nghĩa Lâm",
    "is_difficult_area_from_roadmap": true
  },
  {
    "target_year": 2027,
    "order": 18,
    "commune_name": "Xã Nghĩa Mai",
    "is_difficult_area_from_roadmap": true
  },
  {
    "target_year": 2027,
    "order": 19,
    "commune_name": "Xã Quan Thành",
    "is_difficult_area_from_roadmap": false
  },
  {
    "target_year": 2027,
    "order": 20,
    "commune_name": "Xã Quảng Châu",
    "is_difficult_area_from_roadmap": false
  },
  {
    "target_year": 2027,
    "order": 21,
    "commune_name": "Xã Quỳnh Anh",
    "is_difficult_area_from_roadmap": false
  },
  {
    "target_year": 2027,
    "order": 22,
    "commune_name": "Xã Quỳnh Lưu",
    "is_difficult_area_from_roadmap": false
  },
  {
    "target_year": 2027,
    "order": 23,
    "commune_name": "Xã Quỳnh Văn",
    "is_difficult_area_from_roadmap": false
  },
  {
    "target_year": 2027,
    "order": 24,
    "commune_name": "Xã Tân Kỳ",
    "is_difficult_area_from_roadmap": true
  },
  {
    "target_year": 2027,
    "order": 25,
    "commune_name": "Xã Vân Du",
    "is_difficult_area_from_roadmap": true
  },
  {
    "target_year": 2027,
    "order": 26,
    "commune_name": "Xã Yên Thành",
    "is_difficult_area_from_roadmap": false
  },
  {
    "target_year": 2028,
    "order": 1,
    "commune_name": "Phường Cửa Lò",
    "is_difficult_area_from_roadmap": false
  },
  {
    "target_year": 2028,
    "order": 2,
    "commune_name": "Phường Hoàng Mai",
    "is_difficult_area_from_roadmap": false
  },
  {
    "target_year": 2028,
    "order": 3,
    "commune_name": "Phường Quỳnh Mai",
    "is_difficult_area_from_roadmap": false
  },
  {
    "target_year": 2028,
    "order": 4,
    "commune_name": "Phường Tân Mai",
    "is_difficult_area_from_roadmap": false
  },
  {
    "target_year": 2028,
    "order": 5,
    "commune_name": "Xã An Châu",
    "is_difficult_area_from_roadmap": false
  },
  {
    "target_year": 2028,
    "order": 6,
    "commune_name": "Xã Anh Sơn Đông",
    "is_difficult_area_from_roadmap": true
  },
  {
    "target_year": 2028,
    "order": 7,
    "commune_name": "Xã Bắc Lý",
    "is_difficult_area_from_roadmap": true
  },
  {
    "target_year": 2028,
    "order": 8,
    "commune_name": "Xã Bạch Ngọc",
    "is_difficult_area_from_roadmap": true
  },
  {
    "target_year": 2028,
    "order": 9,
    "commune_name": "Xã Bích Hào",
    "is_difficult_area_from_roadmap": true
  },
  {
    "target_year": 2028,
    "order": 10,
    "commune_name": "Xã Cát Ngạn",
    "is_difficult_area_from_roadmap": true
  },
  {
    "target_year": 2028,
    "order": 11,
    "commune_name": "Xã Châu Bình",
    "is_difficult_area_from_roadmap": true
  },
  {
    "target_year": 2028,
    "order": 12,
    "commune_name": "Xã Châu Khê",
    "is_difficult_area_from_roadmap": true
  },
  {
    "target_year": 2028,
    "order": 13,
    "commune_name": "Xã Châu Tiến",
    "is_difficult_area_from_roadmap": true
  },
  {
    "target_year": 2028,
    "order": 14,
    "commune_name": "Xã Con Cuông",
    "is_difficult_area_from_roadmap": true
  },
  {
    "target_year": 2028,
    "order": 15,
    "commune_name": "Xã Đại Đồng",
    "is_difficult_area_from_roadmap": false
  },
  {
    "target_year": 2028,
    "order": 16,
    "commune_name": "Xã Đại Huệ",
    "is_difficult_area_from_roadmap": false
  },
  {
    "target_year": 2028,
    "order": 17,
    "commune_name": "Xã Đô Lương",
    "is_difficult_area_from_roadmap": false
  },
  {
    "target_year": 2028,
    "order": 18,
    "commune_name": "Xã Đông Thành",
    "is_difficult_area_from_roadmap": false
  },
  {
    "target_year": 2028,
    "order": 19,
    "commune_name": "Xã Giai Lạc",
    "is_difficult_area_from_roadmap": false
  },
  {
    "target_year": 2028,
    "order": 20,
    "commune_name": "Xã Hạnh Lâm",
    "is_difficult_area_from_roadmap": true
  },
  {
    "target_year": 2028,
    "order": 21,
    "commune_name": "Xã Hoa Quân",
    "is_difficult_area_from_roadmap": true
  },
  {
    "target_year": 2028,
    "order": 22,
    "commune_name": "Xã Hợp Minh",
    "is_difficult_area_from_roadmap": false
  },
  {
    "target_year": 2028,
    "order": 23,
    "commune_name": "Xã Hưng Nguyên",
    "is_difficult_area_from_roadmap": false
  },
  {
    "target_year": 2028,
    "order": 24,
    "commune_name": "Xã Hưng Nguyên Nam",
    "is_difficult_area_from_roadmap": false
  },
  {
    "target_year": 2028,
    "order": 25,
    "commune_name": "Xã Huồi Tụ",
    "is_difficult_area_from_roadmap": true
  },
  {
    "target_year": 2028,
    "order": 26,
    "commune_name": "Xã Keng Đu",
    "is_difficult_area_from_roadmap": true
  },
  {
    "target_year": 2028,
    "order": 27,
    "commune_name": "Xã Lam Thành",
    "is_difficult_area_from_roadmap": false
  },
  {
    "target_year": 2028,
    "order": 28,
    "commune_name": "Xã Lương Sơn",
    "is_difficult_area_from_roadmap": false
  },
  {
    "target_year": 2028,
    "order": 29,
    "commune_name": "Xã Minh Châu",
    "is_difficult_area_from_roadmap": false
  },
  {
    "target_year": 2028,
    "order": 30,
    "commune_name": "Xã Minh Hợp",
    "is_difficult_area_from_roadmap": true
  },
  {
    "target_year": 2028,
    "order": 31,
    "commune_name": "Xã Môn Sơn",
    "is_difficult_area_from_roadmap": true
  },
  {
    "target_year": 2028,
    "order": 32,
    "commune_name": "Xã Mường Lống",
    "is_difficult_area_from_roadmap": true
  },
  {
    "target_year": 2028,
    "order": 33,
    "commune_name": "Xã Mường Quàng",
    "is_difficult_area_from_roadmap": true
  },
  {
    "target_year": 2028,
    "order": 34,
    "commune_name": "Xã Mường Típ",
    "is_difficult_area_from_roadmap": true
  },
  {
    "target_year": 2028,
    "order": 35,
    "commune_name": "Xã Na Loi",
    "is_difficult_area_from_roadmap": true
  },
  {
    "target_year": 2028,
    "order": 36,
    "commune_name": "Xã Na Ngoi",
    "is_difficult_area_from_roadmap": true
  },
  {
    "target_year": 2028,
    "order": 37,
    "commune_name": "Xã Nam Đàn",
    "is_difficult_area_from_roadmap": false
  },
  {
    "target_year": 2028,
    "order": 38,
    "commune_name": "Xã Nghĩa Khánh",
    "is_difficult_area_from_roadmap": true
  },
  {
    "target_year": 2028,
    "order": 39,
    "commune_name": "Xã Nghĩa Thọ",
    "is_difficult_area_from_roadmap": true
  },
  {
    "target_year": 2028,
    "order": 40,
    "commune_name": "Xã Nhôn Mai",
    "is_difficult_area_from_roadmap": true
  },
  {
    "target_year": 2028,
    "order": 41,
    "commune_name": "Xã Quang Đồng",
    "is_difficult_area_from_roadmap": true
  },
  {
    "target_year": 2028,
    "order": 42,
    "commune_name": "Xã Quế Phong",
    "is_difficult_area_from_roadmap": true
  },
  {
    "target_year": 2028,
    "order": 43,
    "commune_name": "Xã Quỳ Châu",
    "is_difficult_area_from_roadmap": true
  },
  {
    "target_year": 2028,
    "order": 44,
    "commune_name": "Xã Quỳ Hợp",
    "is_difficult_area_from_roadmap": true
  },
  {
    "target_year": 2028,
    "order": 45,
    "commune_name": "Xã Quỳnh Sơn",
    "is_difficult_area_from_roadmap": false
  },
  {
    "target_year": 2028,
    "order": 46,
    "commune_name": "Xã Quỳnh Tam",
    "is_difficult_area_from_roadmap": true
  },
  {
    "target_year": 2028,
    "order": 47,
    "commune_name": "Xã Quỳnh Thắng",
    "is_difficult_area_from_roadmap": true
  },
  {
    "target_year": 2028,
    "order": 48,
    "commune_name": "Xã Tam Đồng",
    "is_difficult_area_from_roadmap": true
  },
  {
    "target_year": 2028,
    "order": 49,
    "commune_name": "Xã Tam Hợp",
    "is_difficult_area_from_roadmap": true
  },
  {
    "target_year": 2028,
    "order": 50,
    "commune_name": "Xã Tam Quang",
    "is_difficult_area_from_roadmap": true
  },
  {
    "target_year": 2028,
    "order": 51,
    "commune_name": "Xã Tam Thái",
    "is_difficult_area_from_roadmap": true
  },
  {
    "target_year": 2028,
    "order": 52,
    "commune_name": "Xã Thành Bình Thọ",
    "is_difficult_area_from_roadmap": true
  },
  {
    "target_year": 2028,
    "order": 53,
    "commune_name": "Xã Thiên Nhẫn",
    "is_difficult_area_from_roadmap": false
  },
  {
    "target_year": 2028,
    "order": 54,
    "commune_name": "Xã Thông Thụ",
    "is_difficult_area_from_roadmap": true
  },
  {
    "target_year": 2028,
    "order": 55,
    "commune_name": "Xã Vạn An",
    "is_difficult_area_from_roadmap": false
  },
  {
    "target_year": 2028,
    "order": 56,
    "commune_name": "Xã Văn Kiều",
    "is_difficult_area_from_roadmap": false
  },
  {
    "target_year": 2028,
    "order": 57,
    "commune_name": "Xã Vân Tụ",
    "is_difficult_area_from_roadmap": false
  },
  {
    "target_year": 2028,
    "order": 58,
    "commune_name": "Xã Vĩnh Tường",
    "is_difficult_area_from_roadmap": true
  },
  {
    "target_year": 2028,
    "order": 59,
    "commune_name": "Xã Xuân Lâm",
    "is_difficult_area_from_roadmap": true
  },
  {
    "target_year": 2028,
    "order": 60,
    "commune_name": "Xã Yên Hòa",
    "is_difficult_area_from_roadmap": true
  },
  {
    "target_year": 2028,
    "order": 61,
    "commune_name": "Xã Yên Xuân",
    "is_difficult_area_from_roadmap": true
  },
  {
    "target_year": 2029,
    "order": 1,
    "commune_name": "Xã Bình Chuẩn",
    "is_difficult_area_from_roadmap": true
  },
  {
    "target_year": 2029,
    "order": 2,
    "commune_name": "Xã Châu Hồng",
    "is_difficult_area_from_roadmap": true
  },
  {
    "target_year": 2029,
    "order": 3,
    "commune_name": "Xã Châu Lộc",
    "is_difficult_area_from_roadmap": true
  },
  {
    "target_year": 2029,
    "order": 4,
    "commune_name": "Xã Chiêu Lưu",
    "is_difficult_area_from_roadmap": true
  },
  {
    "target_year": 2029,
    "order": 5,
    "commune_name": "Xã Giai Xuân",
    "is_difficult_area_from_roadmap": true
  },
  {
    "target_year": 2029,
    "order": 6,
    "commune_name": "Xã Hùng Châu",
    "is_difficult_area_from_roadmap": false
  },
  {
    "target_year": 2029,
    "order": 7,
    "commune_name": "Xã Hữu Khuông",
    "is_difficult_area_from_roadmap": true
  },
  {
    "target_year": 2029,
    "order": 8,
    "commune_name": "Xã Hữu Kiệm",
    "is_difficult_area_from_roadmap": true
  },
  {
    "target_year": 2029,
    "order": 9,
    "commune_name": "Xã Kim Bảng",
    "is_difficult_area_from_roadmap": true
  },
  {
    "target_year": 2029,
    "order": 10,
    "commune_name": "Xã Lượng Minh",
    "is_difficult_area_from_roadmap": true
  },
  {
    "target_year": 2029,
    "order": 11,
    "commune_name": "Xã Mường Chọng",
    "is_difficult_area_from_roadmap": true
  },
  {
    "target_year": 2029,
    "order": 12,
    "commune_name": "Xã Mường Ham",
    "is_difficult_area_from_roadmap": true
  },
  {
    "target_year": 2029,
    "order": 13,
    "commune_name": "Xã Mường Xén",
    "is_difficult_area_from_roadmap": true
  },
  {
    "target_year": 2029,
    "order": 14,
    "commune_name": "Xã Mỹ Lý",
    "is_difficult_area_from_roadmap": true
  },
  {
    "target_year": 2029,
    "order": 15,
    "commune_name": "Xã Nậm Cắn",
    "is_difficult_area_from_roadmap": true
  },
  {
    "target_year": 2029,
    "order": 16,
    "commune_name": "Xã Nga My",
    "is_difficult_area_from_roadmap": true
  },
  {
    "target_year": 2029,
    "order": 17,
    "commune_name": "Xã Nghĩa Đàn",
    "is_difficult_area_from_roadmap": true
  },
  {
    "target_year": 2029,
    "order": 18,
    "commune_name": "Xã Nghĩa Hành",
    "is_difficult_area_from_roadmap": true
  },
  {
    "target_year": 2029,
    "order": 19,
    "commune_name": "Xã Nghĩa Hưng",
    "is_difficult_area_from_roadmap": true
  },
  {
    "target_year": 2029,
    "order": 20,
    "commune_name": "Xã Nghĩa Lộc",
    "is_difficult_area_from_roadmap": true
  },
  {
    "target_year": 2029,
    "order": 21,
    "commune_name": "Xã Sơn Lâm",
    "is_difficult_area_from_roadmap": true
  },
  {
    "target_year": 2029,
    "order": 22,
    "commune_name": "Xã Tân Phú",
    "is_difficult_area_from_roadmap": true
  },
  {
    "target_year": 2029,
    "order": 23,
    "commune_name": "Xã Thần Lĩnh",
    "is_difficult_area_from_roadmap": false
  },
  {
    "target_year": 2029,
    "order": 24,
    "commune_name": "Xã Thuần Trung",
    "is_difficult_area_from_roadmap": false
  },
  {
    "target_year": 2029,
    "order": 25,
    "commune_name": "Xã Tiền Phong",
    "is_difficult_area_from_roadmap": true
  },
  {
    "target_year": 2029,
    "order": 26,
    "commune_name": "Xã Tri Lễ",
    "is_difficult_area_from_roadmap": true
  },
  {
    "target_year": 2029,
    "order": 27,
    "commune_name": "Xã Yên Na",
    "is_difficult_area_from_roadmap": true
  },
  {
    "target_year": 2029,
    "order": 28,
    "commune_name": "Xã Yên Trung",
    "is_difficult_area_from_roadmap": false
  }
]


def _norm(text: str) -> str:
    value = unicodedata.normalize("NFD", str(text or "").strip().upper())
    value = "".join(ch for ch in value if unicodedata.category(ch) != "Mn")
    value = value.replace("Đ", "D")
    return " ".join(value.split())


def _norm_without_prefix(text: str) -> str:
    value = _norm(text)
    for prefix in ("XA ", "PHUONG ", "THI TRAN "):
        if value.startswith(prefix):
            return value[len(prefix):].strip()
    return value


def _backup(path: Path) -> None:
    if not path.exists():
        return
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, BACKUP_DIR / path.name)


def _restore(path: Path) -> None:
    backup = BACKUP_DIR / path.name
    if backup.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(backup, path)
    elif path.exists():
        path.unlink()


def _db_match_report(records: list[dict]) -> list[str]:
    db = PROJECT / "data" / "phocap.db"
    rows = []

    if not db.exists():
        return [f"Không tìm thấy DB để đối chiếu xã/phường: {db}"]

    conn = sqlite3.connect(str(db))
    try:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        fk = conn.execute("PRAGMA foreign_key_check").fetchall()
        rows.append(f"integrity_check: {integrity}")
        rows.append(f"foreign_key_check: {len(fk)} lỗi")

        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }

        table = "communes" if "communes" in tables else None
        if not table:
            rows.append("Không tìm thấy bảng communes; bỏ qua đối chiếu tên.")
            return rows

        info = conn.execute('PRAGMA table_info("communes")').fetchall()
        columns = [row[1] for row in info]
        id_col = "id" if "id" in columns else None

        name_col = None
        for candidate in ("name", "commune_name", "display_name", "title"):
            if candidate in columns:
                name_col = candidate
                break

        if not id_col or not name_col:
            rows.append(
                "Bảng communes không có cột id/name quen thuộc; "
                "bỏ qua đối chiếu tự động."
            )
            return rows

        db_rows = conn.execute(
            f'SELECT "{id_col}", "{name_col}" FROM "communes"'
        ).fetchall()

        exact = {}
        no_prefix = {}

        for cid, name in db_rows:
            exact.setdefault(_norm(name), []).append((cid, name))
            no_prefix.setdefault(_norm_without_prefix(name), []).append((cid, name))

        matched = 0
        unmatched = []
        ambiguous = []

        for item in records:
            name = item["commune_name"]
            candidates = exact.get(_norm(name), [])

            if not candidates:
                candidates = no_prefix.get(_norm_without_prefix(name), [])

            if len(candidates) == 1:
                matched += 1
            elif len(candidates) == 0:
                unmatched.append(name)
            else:
                ambiguous.append((name, candidates))

        rows.append(f"Tổng lộ trình: {len(records)} xã/phường")
        rows.append(f"Khớp duy nhất với DB: {matched}")
        rows.append(f"Chưa khớp: {len(unmatched)}")
        rows.append(f"Khớp nhiều: {len(ambiguous)}")

        if unmatched:
            rows.append("")
            rows.append("CHƯA KHỚP:")
            rows.extend(f" - {name}" for name in unmatched)

        if ambiguous:
            rows.append("")
            rows.append("KHỚP NHIỀU:")
            for name, candidates in ambiguous:
                rows.append(
                    f" - {name} -> "
                    + ", ".join(f"{cid}:{cname}" for cid, cname in candidates)
                )

    finally:
        conn.close()

    return rows


def main() -> None:
    print("=" * 132)
    print(
        "BÀI 13B-11.15.2.4.4 - "
        "CHUẨN HÓA QUY TẮC NGHIỆP VỤ + LỘ TRÌNH CÔNG NHẬN"
    )
    print("=" * 132)
    print()
    print("SẼ TẠO:")
    print(" - app\\services\\pcgd_business_rules.py")
    print(" - app\\data\\pcgd_recognition_roadmap_2026_2030.json")
    print()
    print("KHÔNG LÀM:")
    print(" - Không sửa database.")
    print(" - Không sửa route/menu/template.")
    print(" - Không nối builder báo cáo ở bài này.")
    print(" - Không tự đổi vùng khó khăn thành 'đặc biệt khó khăn' pháp lý.")
    print()

    if not APP.exists():
        raise SystemExit(f"Không tìm thấy thư mục app: {APP}")

    records = json.loads(ROADMAP_RECORDS)

    # Kiểm tra dữ liệu lộ trình trước khi ghi.
    assert len(records) == 130, len(records)

    year_counts = {
        year: sum(1 for item in records if item["target_year"] == year)
        for year in (2026, 2027, 2028, 2029)
    }
    assert year_counts == {2026: 15, 2027: 26, 2028: 61, 2029: 28}, year_counts

    difficult_count = sum(
        1 for item in records if item["is_difficult_area_from_roadmap"]
    )
    assert difficult_count == 79, difficult_count

    names = [item["commune_name"] for item in records]
    assert len(names) == len(set(names)), "Lộ trình có xã/phường trùng tên."

    # Parse module trước khi đụng file thật.
    ast.parse(SERVICE_CONTENT)

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    _backup(SERVICE_FILE)
    _backup(ROADMAP_FILE)

    SERVICES.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    EXPORTS.mkdir(parents=True, exist_ok=True)

    try:
        SERVICE_FILE.write_text(SERVICE_CONTENT, encoding="utf-8")

        payload = {
            "version": "13B-11.15.2.4.4",
            "source_file": "Lộ trình công nhận phổ cập.xlsx",
            "program_code": "PCGDMN_3_5",
            "scope": "Nghệ An",
            "note": (
                "Tên màu đỏ trong file người dùng cung cấp được lưu là "
                "is_difficult_area_from_roadmap=true. "
                "Không tự động đồng nhất cờ này với khái niệm "
                "'xã có điều kiện kinh tế - xã hội đặc biệt khó khăn' "
                "trong Nghị định 20/2014/NĐ-CP và 277/2025/NĐ-CP."
            ),
            "counts": {
                "total": len(records),
                "by_year": year_counts,
                "difficult_area_from_roadmap": difficult_count,
            },
            "records": records,
        }

        ROADMAP_FILE.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # Verify lại file đã ghi.
        ast.parse(SERVICE_FILE.read_text(encoding="utf-8"))
        check_payload = json.loads(ROADMAP_FILE.read_text(encoding="utf-8"))
        assert len(check_payload["records"]) == 130
        assert check_payload["counts"]["difficult_area_from_roadmap"] == 79

        report = []
        report.append("=" * 132 + "\n")
        report.append("BÀI 13B-11.15.2.4.4 - BÁO CÁO CÀI ĐẶT\n")
        report.append("=" * 132 + "\n\n")
        report.append(f"Service: {SERVICE_FILE}\n")
        report.append(f"Roadmap: {ROADMAP_FILE}\n")
        report.append(f"Tổng xã/phường: {len(records)}\n")
        report.append(f"2026: {year_counts[2026]}\n")
        report.append(f"2027: {year_counts[2027]}\n")
        report.append(f"2028: {year_counts[2028]}\n")
        report.append(f"2029: {year_counts[2029]}\n")
        report.append(f"Chữ đỏ / vùng khó khăn theo file: {difficult_count}\n\n")

        report.append("QUY TẮC ĐÃ CHUẨN HÓA:\n")
        report.append(" - TH: PPC = Tổng số - khuyết tật - chuyển đi - chết.\n")
        report.append(" - TH: tại chỗ / đi nơi khác / nơi khác đến theo phạm vi xã.\n")
        report.append(" - THCS: học/TN THCS theo phạm vi xã.\n")
        report.append(" - THCS sau THCS: tại chỗ = trong tỉnh; nơi khác = ngoài tỉnh.\n")
        report.append(" - GV/lớp TH và THCS = tổng GV cấp học / tổng lớp cấp học toàn xã.\n")
        report.append(" - Điểm trường = số điểm lẻ.\n")
        report.append(" - Ngưỡng TH/THCS/XMC theo NĐ20/2014/NĐ-CP.\n")
        report.append(" - Ngưỡng PCGDMN 3-5 theo NĐ277/2025/NĐ-CP.\n\n")

        report.append("ĐỐI CHIẾU TÊN XÃ/PHƯỜNG VỚI DB:\n")
        report.append("-" * 132 + "\n")
        for row in _db_match_report(records):
            report.append(row + "\n")

        report.append("\nAN TOÀN:\n")
        report.append(" - Database không thay đổi.\n")
        report.append(" - Route/menu/template không thay đổi.\n")
        report.append(" - Chưa thay đổi kết quả báo cáo hiện hành.\n")
        report.append(
            " - Cờ vùng khó khăn từ lộ trình chưa tự động kích hoạt "
            "ngưỡng 'đặc biệt khó khăn'.\n"
        )

        REPORT_FILE.write_text("".join(report), encoding="utf-8")

    except Exception:
        _restore(SERVICE_FILE)
        _restore(ROADMAP_FILE)
        raise

    print("CÀI ĐẶT THÀNH CÔNG.")
    print(f"Service: {SERVICE_FILE}")
    print(f"Roadmap: {ROADMAP_FILE}")
    print(f"Báo cáo: {REPORT_FILE}")
    print()
    print("Database: KHÔNG THAY ĐỔI.")
    print("Báo cáo hiện hành: CHƯA THAY ĐỔI.")
    print()
    print("=" * 132)
    print("BÀI 13B-11.15.2.4.4 THÀNH CÔNG")
    print("=" * 132)


if __name__ == "__main__":
    main()
