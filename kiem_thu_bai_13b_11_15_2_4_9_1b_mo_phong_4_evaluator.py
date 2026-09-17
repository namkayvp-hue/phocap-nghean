# -*- coding: utf-8 -*-
"""
BÀI 13B-11.15.2.4.9.1B
KIỂM THỬ MÔ PHỎNG 4 EVALUATOR - XÃ THƯỜNG / XÃ ĐBKK

- Gọi trực tiếp app.services.pcgd_business_rules.
- Không đọc/ghi database.
- Không sửa source.
- Kiểm tra chênh nhánh ngưỡng, ngưỡng biên và thiếu dữ liệu.
"""

from __future__ import annotations

import hashlib
import inspect
import os
import sys
from datetime import datetime
from pathlib import Path


PROJECT = Path(
    os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")
).resolve()
RULES = PROJECT / "app" / "services" / "pcgd_business_rules.py"
EXPORTS = PROJECT / "exports"
STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
OUT_DIR = EXPORTS / f"kiem_thu_bai_13b_11_15_2_4_9_1b_{STAMP}"
REPORT = OUT_DIR / f"bao_cao_kiem_thu_4_9_1b_{STAMP}.txt"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def text_result(result) -> str:
    if bool(result.passed):
        return f"Đạt Mức {result.level}" if result.level is not None else "Đạt"
    return "Chưa đủ dữ liệu" if tuple(result.missing_fields or ()) else "Không đạt"


def checks(result) -> dict:
    return {
        str(c.key): {
            "actual": c.actual,
            "required": c.required,
            "passed": c.passed,
        }
        for c in (result.checks or ())
    }


def eq(actual, expected, label: str) -> None:
    if actual != expected:
        raise AssertionError(
            f"{label}: actual={actual!r}; expected={expected!r}"
        )


def ok(condition: bool, label: str) -> None:
    if not condition:
        raise AssertionError(label)


def assert_result(result, passed: bool, level, label: str) -> None:
    eq(bool(result.passed), passed, label + " / passed")
    eq(result.level, level, label + " / level")


def show(label: str, result) -> list[str]:
    line = f"{label}: {text_result(result)}"
    print("      " + line)
    rows = [line]
    for c in result.checks or ():
        detail = (
            f"  - {c.key}: actual={c.actual!r}; "
            f"required={c.required!r}; passed={c.passed!r}"
        )
        print("        " + detail.strip())
        rows.append(detail)
    if result.missing_fields:
        missing = "  missing_fields=" + ", ".join(result.missing_fields)
        print("        " + missing.strip())
        rows.append(missing)
    return rows


def verify_module(rules) -> None:
    names = (
        "evaluate_preschool_3_5_commune",
        "evaluate_primary_commune",
        "evaluate_literacy_commune",
        "evaluate_thcs_commune",
    )
    for name in names:
        func = getattr(rules, name, None)
        if not callable(func):
            raise RuntimeError(f"Thiếu evaluator: {name}")
        if "is_special_difficult" not in inspect.signature(func).parameters:
            raise RuntimeError(f"{name} thiếu is_special_difficult")


def test_mn(rules, report: list[str]) -> None:
    print("[2/7] Mầm non")
    metrics = {
        "attendance_rate_3_5": 87.0,
        "completion_rate_3_5_by_age": {3: 82.0, 4: 82.0, 5: 82.0},
    }
    normal = rules.evaluate_preschool_3_5_commune(
        metrics, is_special_difficult=False
    )
    special = rules.evaluate_preschool_3_5_commune(
        metrics, is_special_difficult=True
    )

    assert_result(normal, False, None, "MN thường")
    assert_result(special, True, 1, "MN ĐBKK")

    nc, sc = checks(normal), checks(special)
    eq(nc["attendance_rate_3_5"]["required"], 90.0, "MN thường huy động")
    eq(sc["attendance_rate_3_5"]["required"], 85.0, "MN ĐBKK huy động")
    eq(nc["completion_rate_age_3"]["required"], 85.0, "MN thường hoàn thành")
    eq(sc["completion_rate_age_3"]["required"], 80.0, "MN ĐBKK hoàn thành")

    boundary = rules.evaluate_preschool_3_5_commune(
        {
            "attendance_rate_3_5": 90.0,
            "completion_rate_3_5_by_age": {3: 85.0, 4: 85.0, 5: 85.0},
        },
        is_special_difficult=False,
    )
    assert_result(boundary, True, 1, "MN đúng biên")

    missing = rules.evaluate_preschool_3_5_commune(
        {
            "attendance_rate_3_5": None,
            "completion_rate_3_5_by_age": {3: None, 4: None, 5: None},
        },
        is_special_difficult=False,
    )
    ok(not missing.passed and bool(missing.missing_fields), "MN thiếu dữ liệu")

    report += ["", "MẦM NON", f"metrics={metrics}"]
    report += show("Xã thường", normal)
    report += show("Xã ĐBKK", special)


def test_th(rules, report: list[str]) -> None:
    print("[3/7] Tiểu học")
    metrics = {
        "age6_grade1_rate": 95.0,
        "age14_completed_rate": 75.0,
        "age11_completed_rate": 75.0,
        "age11_remaining_all_study_primary": True,
    }
    normal = rules.evaluate_primary_commune(
        metrics, is_special_difficult=False
    )
    special = rules.evaluate_primary_commune(
        metrics, is_special_difficult=True
    )

    assert_result(normal, False, None, "TH thường")
    assert_result(special, True, 2, "TH ĐBKK")

    nc, sc = checks(normal), checks(special)
    eq(nc["age14_completed_rate"]["required"], 80.0, "TH thường M1")
    eq(sc["age14_completed_rate"]["required"], 70.0, "TH ĐBKK M1")
    eq(sc["age11_completed_rate_L2"]["required"], 70.0, "TH ĐBKK M2")

    boundary = rules.evaluate_primary_commune(
        {
            "age6_grade1_rate": 98.0,
            "age14_completed_rate": 80.0,
            "age11_completed_rate": 90.0,
            "age11_remaining_all_study_primary": True,
        },
        is_special_difficult=False,
    )
    assert_result(boundary, True, 3, "TH đúng biên M3")

    missing = rules.evaluate_primary_commune(
        {
            "age6_grade1_rate": None,
            "age14_completed_rate": None,
            "age11_completed_rate": None,
            "age11_remaining_all_study_primary": None,
        },
        is_special_difficult=False,
    )
    ok(not missing.passed and bool(missing.missing_fields), "TH thiếu dữ liệu")

    report += ["", "TIỂU HỌC", f"metrics={metrics}"]
    report += show("Xã thường", normal)
    report += show("Xã ĐBKK", special)


def test_xmc(rules, report: list[str]) -> None:
    print("[4/7] Xóa mù chữ")
    metrics = {
        "literacy_level1_rate_15_25": 92.0,
        "literacy_level1_rate_15_35": 88.0,
        "literacy_level2_rate_15_35": 92.0,
        "literacy_level2_rate_15_60": 88.0,
    }
    normal = rules.evaluate_literacy_commune(
        metrics, is_special_difficult=False
    )
    special = rules.evaluate_literacy_commune(
        metrics, is_special_difficult=True
    )

    assert_result(normal, False, None, "XMC thường")
    assert_result(special, True, 2, "XMC ĐBKK")

    nc, sc = checks(normal), checks(special)
    ok("literacy_level1_rate_15_35" in nc, "XMC thường phải dùng 15-35")
    ok("literacy_level1_rate_15_25" in sc, "XMC ĐBKK phải dùng 15-25")
    ok("literacy_level2_rate_15_35" in sc, "XMC ĐBKK M2 phải dùng 15-35")

    boundary = rules.evaluate_literacy_commune(
        {
            "literacy_level1_rate_15_25": 90.0,
            "literacy_level1_rate_15_35": 90.0,
            "literacy_level2_rate_15_35": 90.0,
            "literacy_level2_rate_15_60": 90.0,
        },
        is_special_difficult=False,
    )
    assert_result(boundary, True, 2, "XMC đúng biên M2")

    missing = rules.evaluate_literacy_commune(
        {
            "literacy_level1_rate_15_25": None,
            "literacy_level1_rate_15_35": None,
            "literacy_level2_rate_15_35": None,
            "literacy_level2_rate_15_60": None,
        },
        is_special_difficult=False,
    )
    ok(not missing.passed and bool(missing.missing_fields), "XMC thiếu dữ liệu")

    report += ["", "XÓA MÙ CHỮ", f"metrics={metrics}"]
    report += show("Xã thường", normal)
    report += show("Xã ĐBKK", special)


def test_thcs(rules, report: list[str]) -> None:
    print("[5/7] THCS")
    metrics = {
        "age15_18_graduated_thcs_rate": 85.0,
        "age15_18_upper_program_rate": 75.0,
    }
    normal = rules.evaluate_thcs_commune(
        metrics,
        primary_level=2,
        literacy_level=2,
        is_special_difficult=False,
    )
    special = rules.evaluate_thcs_commune(
        metrics,
        primary_level=2,
        literacy_level=2,
        is_special_difficult=True,
    )

    assert_result(normal, True, 1, "THCS thường")
    assert_result(special, True, 2, "THCS ĐBKK")

    nc, sc = checks(normal), checks(special)
    eq(nc["age15_18_graduated_thcs_rate_L1"]["required"], 80.0, "THCS thường M1")
    eq(sc["age15_18_graduated_thcs_rate_L1"]["required"], 70.0, "THCS ĐBKK M1")
    eq(nc["age15_18_graduated_thcs_rate_L2"]["required"], 90.0, "THCS thường M2")
    eq(sc["age15_18_graduated_thcs_rate_L2"]["required"], 80.0, "THCS ĐBKK M2")

    boundary = rules.evaluate_thcs_commune(
        {
            "age15_18_graduated_thcs_rate": 95.0,
            "age15_18_upper_program_rate": 80.0,
        },
        primary_level=2,
        literacy_level=2,
        is_special_difficult=False,
    )
    assert_result(boundary, True, 3, "THCS đúng biên M3")

    missing = rules.evaluate_thcs_commune(
        {
            "age15_18_graduated_thcs_rate": 95.0,
            "age15_18_upper_program_rate": 80.0,
        },
        primary_level=None,
        literacy_level=None,
        is_special_difficult=False,
    )
    ok(not missing.passed and bool(missing.missing_fields), "THCS thiếu prerequisite")

    report += ["", "THCS", f"metrics={metrics}", "primary_level=2; literacy_level=2"]
    report += show("Xã thường", normal)
    report += show("Xã ĐBKK", special)


def main() -> int:
    print("=" * 96)
    print("BÀI 13B-11.15.2.4.9.1B - KIỂM THỬ MÔ PHỎNG 4 EVALUATOR")
    print("=" * 96)
    print()

    if not RULES.exists():
        print(f"[LỖI] Không tìm thấy: {RULES}")
        return 1

    before = sha256(RULES)
    old_cwd = Path.cwd()
    report = [
        "=" * 96,
        "BÀI 13B-11.15.2.4.9.1B - BÁO CÁO KIỂM THỬ",
        "=" * 96,
        f"Rules={RULES}",
        f"SHA256 trước={before}",
        "Không đọc/ghi database.",
    ]

    try:
        sys.path.insert(0, str(PROJECT))
        os.chdir(PROJECT)

        from app.services import pcgd_business_rules as rules

        verify_module(rules)
        print("[1/7] Import 4 evaluator thật: OK")

        test_mn(rules, report)
        test_th(rules, report)
        test_xmc(rules, report)
        test_thcs(rules, report)

        print("[6/7] Test biên + thiếu dữ liệu: ĐẠT")

        after = sha256(RULES)
        eq(after, before, "SHA256 source trước/sau")

        OUT_DIR.mkdir(parents=True, exist_ok=False)
        report += [
            "",
            f"SHA256 sau={after}",
            "Source không thay đổi.",
            "",
            "KẾT LUẬN:",
            "- Mầm non: nhánh thường/ĐBKK hoạt động.",
            "- Tiểu học: nhánh thường/ĐBKK hoạt động.",
            "- XMC: nhánh dải tuổi thường/ĐBKK hoạt động.",
            "- THCS: nhánh thường/ĐBKK hoạt động.",
            "- Ngưỡng biên dùng >=.",
            "- Thiếu dữ liệu không bị suy đoán thành Đạt.",
            "",
            "BÀI 4.9.1B: ĐẠT.",
        ]
        REPORT.write_text("\n".join(report), encoding="utf-8-sig")

        print(f"[7/7] Báo cáo: {REPORT}")
        print()
        print("=" * 96)
        print("BÀI 4.9.1B HOÀN THÀNH - 4/4 EVALUATOR ĐẠT.")
        print("Không đọc/ghi database. Không sửa source.")
        print("=" * 96)
        return 0

    except Exception as exc:
        print()
        print("=" * 96)
        print("[LỖI] BÀI 4.9.1B CHƯA ĐẠT")
        print(str(exc))
        print("=" * 96)
        print("Script không có thao tác database.")
        return 1

    finally:
        os.chdir(old_cwd)


if __name__ == "__main__":
    raise SystemExit(main())
