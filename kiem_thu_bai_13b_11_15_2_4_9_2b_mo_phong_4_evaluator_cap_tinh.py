# -*- coding: utf-8 -*-
"""
BÀI 13B-11.15.2.4.9.2B
KIỂM THỬ MÔ PHỎNG 4 EVALUATOR CẤP TỈNH

Gọi trực tiếp evaluator THẬT trong:
    app.services.pcgd_business_rules

Không sửa source.
Không đọc/ghi database.

Kiểm tra:
1. PCGDMN 3-5 tuổi:
   - ĐBKK >=85%
   - nhóm còn lại >=90%
2. Tiểu học:
   - M1/M2/M3 >=90% số xã
3. XMC:
   - M1 >=81%
   - M2 >=90%
4. THCS:
   - M1 >=90%
   - M2 >=95%
   - M3 =100%
5. Kiểm tra đúng ngưỡng biên.
6. Kiểm tra trường hợp chưa đủ dữ liệu có thể làm thay đổi kết luận.
7. SHA256 source trước/sau không thay đổi.
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

RULES = (
    PROJECT
    / "app"
    / "services"
    / "pcgd_business_rules.py"
)

EXPORTS = PROJECT / "exports"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

OUT_DIR = (
    EXPORTS
    / f"kiem_thu_bai_13b_11_15_2_4_9_2b_{STAMP}"
)

REPORT = (
    OUT_DIR
    / f"bao_cao_kiem_thu_4_9_2b_{STAMP}.txt"
)


def sha256(path: Path) -> str:
    h = hashlib.sha256()

    with path.open("rb") as f:
        for chunk in iter(
            lambda: f.read(1024 * 1024),
            b"",
        ):
            h.update(chunk)

    return h.hexdigest()


def eq(actual, expected, label: str):
    if actual != expected:
        raise AssertionError(
            f"{label}: actual={actual!r}; "
            f"expected={expected!r}"
        )


def ok(condition: bool, label: str):
    if not condition:
        raise AssertionError(label)


def result_text(result):
    if bool(result.passed):
        return (
            f"Đạt Mức {result.level}"
            if result.level is not None
            else "Đạt"
        )

    if tuple(
        getattr(
            result,
            "missing_fields",
            (),
        )
        or ()
    ):
        return "Chưa đủ dữ liệu"

    return "Không đạt"


def show(label: str, result, lines: list[str]):
    text = f"{label}: {result_text(result)}"
    print("      " + text)
    lines.append(text)

    for check in (
        getattr(
            result,
            "checks",
            (),
        )
        or ()
    ):
        row = (
            f"  - {check.key}: "
            f"actual={check.actual!r}; "
            f"required={check.required!r}; "
            f"passed={check.passed!r}; "
            f"note={getattr(check, 'note', '')!r}"
        )

        print(
            "        "
            + row.strip()
        )

        lines.append(row)

    missing = tuple(
        getattr(
            result,
            "missing_fields",
            (),
        )
        or ()
    )

    if missing:
        row = (
            "  missing_fields="
            + ", ".join(missing)
        )

        print(
            "        "
            + row.strip()
        )

        lines.append(row)


def verify_functions(rules):
    required = (
        "evaluate_preschool_3_5_province",
        "evaluate_primary_province",
        "evaluate_literacy_province",
        "evaluate_thcs_province",
    )

    for name in required:
        fn = getattr(
            rules,
            name,
            None,
        )

        if not callable(fn):
            raise RuntimeError(
                f"Thiếu evaluator cấp tỉnh: {name}"
            )


def test_mn(rules, report):
    print("[2/7] PCGDMN 3-5 cấp tỉnh")

    # 51 xã ĐBKK: 44/51 = 86.27% >=85
    # 79 xã còn lại: 72/79 = 91.14% >=90
    passed = (
        rules.evaluate_preschool_3_5_province(
            special_difficult_commune_statuses=(
                [True] * 44
                + [False] * 7
            ),
            other_commune_statuses=(
                [True] * 72
                + [False] * 7
            ),
        )
    )

    show(
        "Ca đạt",
        passed,
        report,
    )

    ok(
        passed.passed is True,
        "MN cấp tỉnh ca đạt",
    )

    # 43/51 = 84.31% <85
    failed = (
        rules.evaluate_preschool_3_5_province(
            special_difficult_commune_statuses=(
                [True] * 43
                + [False] * 8
            ),
            other_commune_statuses=(
                [True] * 72
                + [False] * 7
            ),
        )
    )

    show(
        "Ca không đạt",
        failed,
        report,
    )

    ok(
        failed.passed is False
        and not failed.missing_fields,
        "MN cấp tỉnh ca không đạt",
    )

    # 43 chắc chắn đạt + 1 chưa rõ ở nhóm ĐBKK:
    # min 84.31%; max 86.27% -> chưa đủ dữ liệu.
    uncertain = (
        rules.evaluate_preschool_3_5_province(
            special_difficult_commune_statuses=(
                [True] * 43
                + [None]
                + [False] * 7
            ),
            other_commune_statuses=(
                [True] * 72
                + [False] * 7
            ),
        )
    )

    show(
        "Ca chưa đủ dữ liệu",
        uncertain,
        report,
    )

    ok(
        uncertain.passed is False
        and bool(
            uncertain.missing_fields
        ),
        "MN cấp tỉnh ca chưa đủ dữ liệu",
    )


def test_primary(rules, report):
    print("[3/7] Tiểu học cấp tỉnh")

    # 117/130 = 90% đạt M3.
    level3 = rules.evaluate_primary_province(
        [{"level": 3, "incomplete": False}] * 117
        + [{"level": 0, "incomplete": False}] * 13
    )

    show(
        "Đúng biên M3",
        level3,
        report,
    )

    eq(
        level3.level,
        3,
        "TH cấp tỉnh M3",
    )
    ok(
        level3.passed is True,
        "TH cấp tỉnh M3 passed",
    )

    # 117 xã đạt M2; trong đó chỉ 116 đạt M3.
    # M1/M2 đạt 90%; M3 không đạt.
    level2 = rules.evaluate_primary_province(
        [{"level": 3, "incomplete": False}] * 116
        + [{"level": 2, "incomplete": False}]
        + [{"level": 0, "incomplete": False}] * 13
    )

    show(
        "Dừng ở M2",
        level2,
        report,
    )

    eq(
        level2.level,
        2,
        "TH cấp tỉnh dừng M2",
    )

    # 116/130 chắc chắn M1 + 1 xã chưa rõ:
    # min 89.23%, max 90.00% -> chưa đủ dữ liệu.
    uncertain = rules.evaluate_primary_province(
        [{"level": 1, "incomplete": False}] * 116
        + [{"level": None, "incomplete": True}]
        + [{"level": 0, "incomplete": False}] * 13
    )

    show(
        "Chưa đủ dữ liệu M1",
        uncertain,
        report,
    )

    ok(
        uncertain.passed is False
        and bool(
            uncertain.missing_fields
        ),
        "TH cấp tỉnh chưa đủ dữ liệu",
    )


def test_literacy(rules, report):
    print("[4/7] Xóa mù chữ cấp tỉnh")

    # M2: 117/130 = 90%
    level2 = rules.evaluate_literacy_province(
        [{"level": 2, "incomplete": False}] * 117
        + [{"level": 0, "incomplete": False}] * 13
    )

    show(
        "Đúng biên M2",
        level2,
        report,
    )

    eq(
        level2.level,
        2,
        "XMC cấp tỉnh M2",
    )

    # M1: ceil(81%*130)=106 xã.
    # 106/130 = 81.538...%
    level1 = rules.evaluate_literacy_province(
        [{"level": 1, "incomplete": False}] * 106
        + [{"level": 0, "incomplete": False}] * 24
    )

    show(
        "Đạt M1",
        level1,
        report,
    )

    eq(
        level1.level,
        1,
        "XMC cấp tỉnh M1",
    )

    # 105 xã chắc chắn M1 + 1 chưa rõ.
    # 105/130=80.77; max 106/130=81.54 -> chưa đủ.
    uncertain = rules.evaluate_literacy_province(
        [{"level": 1, "incomplete": False}] * 105
        + [{"level": None, "incomplete": True}]
        + [{"level": 0, "incomplete": False}] * 24
    )

    show(
        "Chưa đủ dữ liệu M1",
        uncertain,
        report,
    )

    ok(
        uncertain.passed is False
        and bool(
            uncertain.missing_fields
        ),
        "XMC cấp tỉnh chưa đủ dữ liệu",
    )


def test_thcs(rules, report):
    print("[5/7] THCS cấp tỉnh")

    # M3 cần 100%.
    level3 = rules.evaluate_thcs_province(
        [{"level": 3, "incomplete": False}] * 130
    )

    show(
        "Đúng biên M3=100%",
        level3,
        report,
    )

    eq(
        level3.level,
        3,
        "THCS cấp tỉnh M3",
    )

    # 124/130 = 95.38% đạt M2.
    level2 = rules.evaluate_thcs_province(
        [{"level": 2, "incomplete": False}] * 124
        + [{"level": 0, "incomplete": False}] * 6
    )

    show(
        "Đạt M2",
        level2,
        report,
    )

    eq(
        level2.level,
        2,
        "THCS cấp tỉnh M2",
    )

    # 117/130=90% đạt M1, nhưng không đủ M2.
    level1 = rules.evaluate_thcs_province(
        [{"level": 1, "incomplete": False}] * 117
        + [{"level": 0, "incomplete": False}] * 13
    )

    show(
        "Đúng biên M1",
        level1,
        report,
    )

    eq(
        level1.level,
        1,
        "THCS cấp tỉnh M1",
    )

    # 129 xã chắc chắn M3 + 1 xã chưa rõ:
    # min=99.23%, max=100% -> M3 chưa đủ dữ liệu,
    # nhưng M1/M2 đã chắc chắn đạt.
    uncertain_high = (
        rules.evaluate_thcs_province(
            [{"level": 3, "incomplete": False}] * 129
            + [{"level": None, "incomplete": True}]
        )
    )

    show(
        "Thiếu dữ liệu ở M3",
        uncertain_high,
        report,
    )

    eq(
        uncertain_high.level,
        2,
        "THCS thiếu dữ liệu M3 vẫn chắc chắn M2",
    )
    ok(
        uncertain_high.passed is True
        and bool(
            uncertain_high.missing_fields
        ),
        "THCS thiếu dữ liệu M3",
    )


def main():
    print("=" * 104)
    print(
        "BÀI 13B-11.15.2.4.9.2B - "
        "KIỂM THỬ MÔ PHỎNG 4 EVALUATOR CẤP TỈNH"
    )
    print("=" * 104)
    print()

    if not RULES.exists():
        print(
            f"[LỖI] Không tìm thấy: {RULES}"
        )
        return 1

    before = sha256(RULES)

    report = [
        "=" * 104,
        "BÀI 13B-11.15.2.4.9.2B - "
        "BÁO CÁO KIỂM THỬ MÔ PHỎNG CẤP TỈNH",
        "=" * 104,
        "",
        f"Rules: {RULES}",
        f"SHA256 trước: {before}",
        "Không đọc/ghi database.",
        "",
    ]

    old_cwd = Path.cwd()

    try:
        os.chdir(PROJECT)
        sys.path.insert(
            0,
            str(PROJECT),
        )

        from app.services import (
            pcgd_business_rules as rules,
        )

        verify_functions(rules)

        print(
            "[1/7] Import 4 evaluator cấp tỉnh: OK"
        )

        test_mn(
            rules,
            report,
        )
        test_primary(
            rules,
            report,
        )
        test_literacy(
            rules,
            report,
        )
        test_thcs(
            rules,
            report,
        )

        print(
            "[6/7] Ngưỡng biên + "
            "ca chưa đủ dữ liệu: ĐẠT"
        )

        after = sha256(RULES)

        eq(
            after,
            before,
            "SHA256 source trước/sau",
        )

        OUT_DIR.mkdir(
            parents=True,
            exist_ok=False,
        )

        report.extend(
            [
                "",
                f"SHA256 sau: {after}",
                "Source không thay đổi.",
                "",
                "KẾT LUẬN:",
                " - PCGDMN cấp tỉnh: ĐẠT kiểm thử.",
                " - Tiểu học cấp tỉnh: ĐẠT kiểm thử.",
                " - XMC cấp tỉnh: ĐẠT kiểm thử.",
                " - THCS cấp tỉnh: ĐẠT kiểm thử.",
                " - Ngưỡng biên: ĐẠT.",
                " - Xử lý chưa đủ dữ liệu: ĐẠT.",
                "",
                "BÀI 4.9.2B: ĐẠT.",
            ]
        )

        REPORT.write_text(
            "\n".join(report),
            encoding="utf-8-sig",
        )

        print(
            f"[7/7] Báo cáo: {REPORT}"
        )

        print()
        print("=" * 104)
        print(
            "BÀI 4.9.2B HOÀN THÀNH - "
            "4/4 EVALUATOR CẤP TỈNH ĐẠT."
        )
        print(
            "Không đọc/ghi database. "
            "Không sửa source."
        )
        print("=" * 104)

        return 0

    except Exception as exc:
        print()
        print("=" * 104)
        print(
            "[LỖI] BÀI 4.9.2B CHƯA ĐẠT"
        )
        print(str(exc))
        print("=" * 104)
        print(
            "Script không có thao tác database."
        )
        return 1

    finally:
        os.chdir(old_cwd)


if __name__ == "__main__":
    raise SystemExit(main())
