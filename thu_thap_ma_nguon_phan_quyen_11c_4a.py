from __future__ import annotations

import csv
import re
import shutil
import zipfile
from collections import Counter
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(r"C:\PhoCap")
APP_ROOT = PROJECT_ROOT / "app"
EXPORT_ROOT = PROJECT_ROOT / "exports"

ROLE_CODES = (
    "SO",
    "XA",
    "TRUONG",
    "GIAO_VIEN",
    "ADMIN",
    "PHONG_BAN",
)

ALLOWED_EXTENSIONS = {".py", ".html"}

EXCLUDED_PART_NAMES = {
    "__pycache__",
    ".git",
    ".idea",
    ".venv",
    "venv",
}

EXCLUDED_FILE_MARKERS = (
    "truoc_sua",
    "_backup",
    ".bak",
    "_old",
    "_copy",
)

ROLE_PATTERN = re.compile(
    r"(?<![A-Z0-9_])("
    + "|".join(re.escape(code) for code in ROLE_CODES)
    + r")(?![A-Z0-9_])"
)


def should_include(path: Path) -> bool:
    if not path.is_file():
        return False

    if path.suffix.lower() not in ALLOWED_EXTENSIONS:
        return False

    lowered_parts = {part.lower() for part in path.parts}
    if lowered_parts.intersection(EXCLUDED_PART_NAMES):
        return False

    lowered_name = path.name.lower()
    if any(marker in lowered_name for marker in EXCLUDED_FILE_MARKERS):
        return False

    return True


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8-sig")


def main() -> None:
    if not APP_ROOT.exists():
        raise FileNotFoundError(
            f"Không tìm thấy thư mục mã nguồn: {APP_ROOT}"
        )

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    package_name = f"nguon_phan_quyen_11c_4_{timestamp}"
    package_dir = EXPORT_ROOT / package_name
    source_dir = package_dir / "source"
    report_txt = package_dir / "bao_cao_phan_quyen.txt"
    report_csv = package_dir / "vi_tri_ma_vai_tro.csv"
    zip_path = EXPORT_ROOT / f"{package_name}.zip"

    if package_dir.exists():
        shutil.rmtree(package_dir)

    source_dir.mkdir(parents=True, exist_ok=True)
    EXPORT_ROOT.mkdir(parents=True, exist_ok=True)

    source_files: list[Path] = []
    occurrences: list[dict[str, str | int]] = []
    file_role_counts: Counter[str] = Counter()
    role_counts: Counter[str] = Counter()

    for path in sorted(APP_ROOT.rglob("*")):
        if not should_include(path):
            continue

        relative = path.relative_to(PROJECT_ROOT)
        text = read_text(path)
        lines = text.splitlines()

        destination = source_dir / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
        source_files.append(relative)

        for line_number, line in enumerate(lines, start=1):
            matches = list(ROLE_PATTERN.finditer(line))
            if not matches:
                continue

            roles_on_line = sorted({match.group(1) for match in matches})
            file_role_counts[str(relative)] += len(matches)

            for role_code in roles_on_line:
                role_counts[role_code] += 1

            occurrences.append(
                {
                    "file": str(relative),
                    "line": line_number,
                    "role_codes": " | ".join(roles_on_line),
                    "content": line.strip(),
                }
            )

    with report_csv.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=("file", "line", "role_codes", "content"),
        )
        writer.writeheader()
        writer.writerows(occurrences)

    report_lines = [
        "BÀI 11C-4 – BÁO CÁO MÃ NGUỒN PHÂN QUYỀN",
        "=" * 72,
        f"Thời điểm tạo: {datetime.now():%d/%m/%Y %H:%M:%S}",
        f"Thư mục dự án: {PROJECT_ROOT}",
        "",
        "PHẠM VI THU THẬP",
        "- Toàn bộ tệp .py và .html hiện hành trong thư mục app.",
        "- Không lấy __pycache__, môi trường ảo hoặc các tệp sao lưu cũ.",
        "- Không đọc hoặc sao chép cơ sở dữ liệu.",
        "",
        f"Tổng số tệp mã nguồn đã sao chép: {len(source_files)}",
        f"Tổng số dòng có mã vai trò: {len(occurrences)}",
        "",
        "SỐ DÒNG THEO MÃ VAI TRÒ",
    ]

    for role_code in ROLE_CODES:
        report_lines.append(
            f"- {role_code}: {role_counts.get(role_code, 0)}"
        )

    report_lines.extend(
        [
            "",
            "SỐ LẦN XUẤT HIỆN THEO TỆP",
        ]
    )

    if file_role_counts:
        for filename, count in file_role_counts.most_common():
            report_lines.append(f"- {filename}: {count}")
    else:
        report_lines.append("- Không tìm thấy mã vai trò trong mã nguồn.")

    report_lines.extend(
        [
            "",
            "DANH SÁCH TỆP ĐÃ SAO CHÉP",
        ]
    )
    report_lines.extend(f"- {path}" for path in source_files)

    report_lines.extend(
        [
            "",
            "KẾT LUẬN",
            "Gói ZIP này chỉ chứa bản sao mã nguồn và báo cáo.",
            "Không có dữ liệu nào trong cơ sở dữ liệu bị thêm, sửa hoặc xóa.",
        ]
    )

    report_txt.write_text(
        "\n".join(report_lines) + "\n",
        encoding="utf-8",
    )

    if zip_path.exists():
        zip_path.unlink()

    with zipfile.ZipFile(
        zip_path,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
    ) as archive:
        for path in sorted(package_dir.rglob("*")):
            if path.is_file():
                archive.write(
                    path,
                    path.relative_to(package_dir).as_posix(),
                )

    print("=" * 72)
    print("BÀI 11C-4A - THU THẬP MÃ NGUỒN PHÂN QUYỀN")
    print("=" * 72)
    print(f"Số tệp .py và .html đã sao chép: {len(source_files)}")
    print(f"Số dòng có mã vai trò: {len(occurrences)}")
    print()
    print("Theo mã vai trò:")
    for role_code in ROLE_CODES:
        print(f"- {role_code}: {role_counts.get(role_code, 0)}")
    print()
    print(f"ĐÃ TẠO GÓI: {zip_path}")
    print()
    print("HOÀN TẤT: chỉ sao chép mã nguồn để kiểm tra.")
    print("Không có dữ liệu nào được thêm, sửa hoặc xóa.")


if __name__ == "__main__":
    main()
