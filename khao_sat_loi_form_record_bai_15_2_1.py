from __future__ import annotations

import ast
import os
import re
from pathlib import Path


PROJECT = Path(
    os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")
).resolve()

ROUTER = PROJECT / "app" / "routers" / "surveys.py"
OUT = (
    PROJECT
    / "exports"
    / "khao_sat_loi_form_record_bai_15_2_1_20260825.txt"
)


def main() -> None:
    print("=" * 110)
    print(
        "KHẢO SÁT CHỈ ĐỌC - LỖI form_record "
        "TRONG route luu_theo_doi_nam_hoc"
    )
    print("=" * 110)
    print()

    if not ROUTER.exists():
        raise SystemExit(
            f"Không tìm thấy: {ROUTER}"
        )

    source = ROUTER.read_text(
        encoding="utf-8-sig"
    )

    tree = ast.parse(source)

    target = None

    for node in ast.walk(tree):
        if isinstance(
            node,
            (
                ast.FunctionDef,
                ast.AsyncFunctionDef,
            ),
        ) and node.name == "luu_theo_doi_nam_hoc":
            target = node
            break

    if target is None:
        raise SystemExit(
            "Không tìm thấy hàm luu_theo_doi_nam_hoc."
        )

    lines = source.splitlines()

    start = target.lineno
    end = target.end_lineno or start

    print(
        f"Hàm: luu_theo_doi_nam_hoc "
        f"(dòng {start} -> {end})"
    )
    print()

    interesting = []

    patterns = (
        "form_record",
        "BAI_13B_11_15_2",
        "study_location_scope",
        "is_repeating_grade",
        "current_education_program",
        "db.commit()",
        "db.add(",
        "SurveyPersonYearRecord",
    )

    for number in range(
        start,
        end + 1,
    ):
        text = lines[
            number - 1
        ]

        if any(
            token in text
            for token in patterns
        ):
            interesting.append(
                number
            )

    print("CÁC DÒNG QUAN TRỌNG:")
    print("-" * 110)

    for number in interesting:
        print(
            f"{number:6}: "
            f"{lines[number - 1]}"
        )

    print()
    print("=" * 110)
    print(
        "VÙNG CHI TIẾT QUANH BLOCK BÀI 15.2.1 "
        "VÀ CÁC ASSIGNMENT form_record"
    )
    print("=" * 110)

    centers = set()

    for number in interesting:
        text = lines[
            number - 1
        ]

        if (
            "form_record" in text
            or "BAI_13B_11_15_2" in text
            or "study_location_scope" in text
        ):
            centers.add(
                number
            )

    # Traceback hiện tại báo khoảng dòng 14647.
    if start <= 14647 <= end:
        centers.add(
            14647
        )

    chunks = []

    for center in sorted(
        centers
    ):
        chunk_start = max(
            start,
            center - 12,
        )

        chunk_end = min(
            end,
            center + 18,
        )

        if chunks and chunk_start <= chunks[-1][1] + 2:
            chunks[-1] = (
                chunks[-1][0],
                max(
                    chunks[-1][1],
                    chunk_end,
                ),
            )
        else:
            chunks.append(
                (
                    chunk_start,
                    chunk_end,
                )
            )

    report_parts = []

    header = (
        "KHẢO SÁT CHỈ ĐỌC - "
        "luu_theo_doi_nam_hoc\n"
        f"Router: {ROUTER}\n"
        f"Hàm: dòng {start} -> {end}\n\n"
    )

    report_parts.append(
        header
    )

    for chunk_start, chunk_end in chunks:
        title = (
            "\n"
            + "=" * 110
            + "\n"
            + f"DÒNG {chunk_start} -> {chunk_end}"
            + "\n"
            + "=" * 110
            + "\n"
        )

        print(
            title,
            end="",
        )

        report_parts.append(
            title
        )

        for number in range(
            chunk_start,
            chunk_end + 1,
        ):
            row = (
                f"{number:6}: "
                f"{lines[number - 1]}"
            )

            print(
                row
            )

            report_parts.append(
                row + "\n"
            )

    OUT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    OUT.write_text(
        "".join(
            report_parts
        ),
        encoding="utf-8",
    )

    print()
    print("=" * 110)
    print("KHẢO SÁT HOÀN TẤT")
    print("=" * 110)
    print(
        "KHÔNG sửa source."
    )
    print(
        "KHÔNG sửa database."
    )
    print(
        "Báo cáo:",
        OUT,
    )


if __name__ == "__main__":
    main()
