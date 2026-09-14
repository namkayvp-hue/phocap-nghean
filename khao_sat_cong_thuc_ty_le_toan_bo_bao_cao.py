from __future__ import annotations

import ast
import os
import re
from datetime import datetime
from pathlib import Path


PROJECT = Path(
    os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")
).resolve()

APP = PROJECT / "app"
EXPORTS = PROJECT / "exports"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
OUT = (
    EXPORTS
    / f"bao_cao_khao_sat_cong_thuc_ty_le_toan_bo_bao_cao_{STAMP}.txt"
)

REPORT_HINTS = (
    "report",
    "bao_cao",
    "pcgd",
    "xmc",
    "mn_official",
    "report_builder",
    "reports",
)

FORMULA_HINTS = (
    "_percent",
    "_pct",
    "percent",
    "percentage",
    "ratio",
    "ty_le",
    "ti_le",
    "tỷ lệ",
    "tỉ lệ",
    "number_format",
    "=IF(",
    "=ROUND(",
    "=SUM(",
    "/100",
    "*100",
)


def read_text(path: Path) -> str:
    try:
        return path.read_text(
            encoding="utf-8-sig",
            errors="strict",
        )
    except UnicodeDecodeError:
        return path.read_text(
            encoding="utf-8",
            errors="replace",
        )


def relevant_file(path: Path) -> bool:
    rel = str(path.relative_to(PROJECT)).lower()

    if any(
        bad in rel
        for bad in (
            "__pycache__",
            "backup",
            "truoc_sua",
            ".bak",
        )
    ):
        return False

    return (
        any(
            hint in rel
            for hint in REPORT_HINTS
        )
        or "structured_report_catalog" in rel
    )


def extract_functions(source: str) -> list[tuple[str, int, int, str]]:
    result = []

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return result

    lines = source.splitlines()

    for node in ast.walk(tree):
        if not isinstance(
            node,
            (
                ast.FunctionDef,
                ast.AsyncFunctionDef,
            ),
        ):
            continue

        start = int(node.lineno)
        end = int(node.end_lineno or start)

        body = "\n".join(
            lines[start - 1:end]
        )

        low = body.lower()

        if any(
            hint.lower() in low
            for hint in FORMULA_HINTS
        ):
            result.append(
                (
                    node.name,
                    start,
                    end,
                    body,
                )
            )

    return result


def formula_lines(
    source: str,
) -> list[tuple[int, str]]:
    rows = []

    for number, line in enumerate(
        source.splitlines(),
        start=1,
    ):
        low = line.lower()

        if any(
            hint.lower() in low
            for hint in FORMULA_HINTS
        ):
            rows.append(
                (
                    number,
                    line.rstrip(),
                )
            )

    return rows


def main() -> None:
    print("=" * 126)
    print(
        "KHẢO SÁT CHỈ ĐỌC - "
        "CÔNG THỨC TỶ LỆ % TRONG TOÀN BỘ BÁO CÁO"
    )
    print("=" * 126)
    print()
    print("MỤC TIÊU:")
    print(
        " - Tìm các hàm _percent/_pct/ratio."
    )
    print(
        " - Tìm công thức Excel hoặc phép tính tỷ lệ."
    )
    print(
        " - Xác định biểu nào đã có logic tự tính."
    )
    print(
        " - Không sửa source/database."
    )
    print()

    if not APP.exists():
        raise SystemExit(
            f"Không tìm thấy: {APP}"
        )

    files = [
        path
        for path in (
            list(APP.rglob("*.py"))
            + list(APP.rglob("*.html"))
        )
        if relevant_file(path)
    ]

    report = []

    report.append(
        "=" * 126 + "\n"
    )
    report.append(
        "KHẢO SÁT CÔNG THỨC TỶ LỆ % TOÀN BỘ BÁO CÁO\n"
    )
    report.append(
        "=" * 126 + "\n\n"
    )
    report.append(
        f"Project: {PROJECT}\n"
    )
    report.append(
        f"Thời điểm: {datetime.now():%d/%m/%Y %H:%M:%S}\n\n"
    )

    found_files = 0

    for path in sorted(files):
        source = read_text(path)

        rows = formula_lines(
            source
        )

        funcs = (
            extract_functions(source)
            if path.suffix.lower() == ".py"
            else []
        )

        if not rows and not funcs:
            continue

        found_files += 1

        rel = path.relative_to(
            PROJECT
        )

        report.append(
            "\n"
            + "=" * 126
            + "\n"
        )
        report.append(
            f"FILE: {rel}\n"
        )
        report.append(
            "=" * 126
            + "\n"
        )

        if funcs:
            report.append(
                "\nHÀM CÓ LOGIC TỶ LỆ:\n"
            )

            for (
                name,
                start,
                end,
                body,
            ) in funcs:
                report.append(
                    f" - {name}: dòng {start}-{end}\n"
                )

                # Chỉ lấy các dòng trọng tâm trong hàm.
                for offset, line in enumerate(
                    body.splitlines(),
                    start=start,
                ):
                    low = line.lower()

                    if any(
                        hint.lower() in low
                        for hint in FORMULA_HINTS
                    ):
                        report.append(
                            f"   {offset:6}: {line.strip()}\n"
                        )

        report.append(
            "\nDÒNG CÓ DẤU VẾT TỶ LỆ/CÔNG THỨC:\n"
        )

        for number, line in rows[:250]:
            report.append(
                f"{number:6}: {line}\n"
            )

        if len(rows) > 250:
            report.append(
                f"... còn {len(rows) - 250} dòng khác\n"
            )

    report.append(
        "\n\n"
        + "=" * 126
        + "\n"
    )
    report.append(
        "KẾT LUẬN KHẢO SÁT\n"
    )
    report.append(
        "=" * 126
        + "\n"
    )
    report.append(
        f"Số file có dấu vết tỷ lệ/công thức: {found_files}\n"
    )
    report.append(
        "Báo cáo này chỉ cho biết source hiện tại có logic tỷ lệ ở đâu.\n"
    )
    report.append(
        "Để xác nhận ĐÚNG NGHIỆP VỤ, cần đối chiếu công thức chính thức "
        "tử số/mẫu số của từng chỉ tiêu trong từng biểu.\n"
    )
    report.append(
        "Không được suy đoán mẫu số hoặc tự biến ô chưa đủ dữ liệu thành 0.\n"
    )

    OUT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    OUT.write_text(
        "".join(report),
        encoding="utf-8",
    )

    print(
        "Khảo sát hoàn tất."
    )
    print(
        "Source/database: KHÔNG THAY ĐỔI."
    )
    print(
        "Báo cáo:",
        OUT,
    )
    print()
    print("=" * 126)
    print(
        "KHẢO SÁT CÔNG THỨC TỶ LỆ THÀNH CÔNG"
    )
    print("=" * 126)


if __name__ == "__main__":
    main()
