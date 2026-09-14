from __future__ import annotations

import os
import re
import shutil
import traceback
from datetime import datetime
from pathlib import Path


PROJECT = Path(
    os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")
).resolve()

TEMPLATES = PROJECT / "app" / "templates"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = (
    PROJECT
    / "exports"
    / f"backup_bai_13b_11_14_7_2_1_{STAMP}"
)

ROUTE = "/doi-ngu/cau-hinh-lop"
LABELS = (
    "4.2.2. Cấu hình lớp",
    "Cấu hình lớp",
)

PREFERRED_HINTS = (
    "menu",
    "partial",
    "dropdown",
    "base",
    "layout",
    "header",
)


def read_text(path: Path) -> str:
    return path.read_text(
        encoding="utf-8-sig",
        errors="strict",
    )


def write_text(path: Path, value: str) -> None:
    path.write_text(
        value,
        encoding="utf-8",
    )


def is_menu_like(path: Path) -> bool:
    low = str(
        path.relative_to(TEMPLATES)
    ).lower()

    return any(
        hint in low
        for hint in PREFERRED_HINTS
    )


def find_candidates() -> list[Path]:
    exact = []
    fallback = []

    for path in TEMPLATES.rglob("*.html"):
        try:
            text = read_text(path)
        except Exception:
            continue

        if ROUTE in text:
            if is_menu_like(path):
                exact.append(path)
            else:
                fallback.append(path)

    return exact or fallback


def remove_menu_item(source: str) -> tuple[str, int]:
    original = source
    removed = 0

    route_escaped = re.escape(ROUTE)

    li_pattern = re.compile(
        r"(?is)<li\b[^>]*>.*?"
        r"<a\b[^>]*href=[\"']"
        + route_escaped
        + r"(?:\?[^\"']*)?[\"'][^>]*>.*?</a>.*?</li>"
    )

    source, count = li_pattern.subn(
        "",
        source,
    )
    removed += count

    a_pattern = re.compile(
        r"(?is)<a\b[^>]*href=[\"']"
        + route_escaped
        + r"(?:\?[^\"']*)?[\"'][^>]*>.*?</a>"
    )

    source, count = a_pattern.subn(
        "",
        source,
    )
    removed += count

    if removed == 0:
        for label in LABELS:
            label_pattern = re.compile(
                r"(?is)<a\b[^>]*>.*?"
                + re.escape(label)
                + r".*?</a>"
            )

            matches = list(
                label_pattern.finditer(source)
            )

            if len(matches) == 1:
                match = matches[0]

                source = (
                    source[:match.start()]
                    + source[match.end():]
                )

                removed += 1
                break

    if removed == 0:
        return original, 0

    return source, removed


def verify_no_menu_link(
    paths: list[Path],
) -> None:
    remaining = []

    pattern = re.compile(
        r"(?is)<a\b[^>]*href=[\"']"
        + re.escape(ROUTE)
    )

    for path in paths:
        text = read_text(path)

        if pattern.search(text):
            remaining.append(path)

    if remaining:
        raise RuntimeError(
            "Sau cài vẫn còn liên kết menu Cấu hình lớp tại: "
            + ", ".join(
                str(p)
                for p in remaining
            )
        )


def main() -> int:
    print("=" * 122)
    print(
        "BÀI 13B-11.14.7.2.1 - "
        "ẨN CẤU HÌNH LỚP KHỎI MENU ĐỘI NGŨ"
    )
    print("=" * 122)
    print()
    print("CHỐT:")
    print(
        " - CSVC là nơi quản lý cơ sở/điểm trường/nhóm-lớp/phòng học."
    )
    print(
        " - Đội ngũ chỉ quản lý dữ liệu CBQL/GV/NV phục vụ biểu GV."
    )
    print()
    print("THỰC HIỆN:")
    print(
        " - Ẩn mục 4.2.2. Cấu hình lớp khỏi menu Đội ngũ."
    )
    print(
        " - KHÔNG xóa route /doi-ngu/cau-hinh-lop."
    )
    print(
        " - KHÔNG sửa database."
    )
    print(
        " - KHÔNG sửa CSVC."
    )
    print()
    print("AN TOÀN:")
    print(
        " - Tự dò file menu chứa đúng route cấu hình lớp."
    )
    print(
        " - Backup file trước khi sửa."
    )
    print(
        " - Có lỗi sẽ khôi phục source."
    )
    print()

    if not TEMPLATES.exists():
        raise RuntimeError(
            f"Không tìm thấy thư mục templates: {TEMPLATES}"
        )

    candidates = find_candidates()

    if not candidates:
        raise RuntimeError(
            "Không tìm thấy template nào chứa route "
            f"{ROUTE}. Không sửa gì."
        )

    print("Template phát hiện:")
    for path in candidates:
        print(
            " -",
            path.relative_to(PROJECT),
        )

    BACKUP.mkdir(
        parents=True,
        exist_ok=False,
    )

    changed: list[Path] = []
    backups: dict[Path, Path] = {}

    try:
        total_removed = 0

        for path in candidates:
            original = read_text(path)

            patched, removed = remove_menu_item(
                original
            )

            if removed <= 0:
                continue

            backup_path = (
                BACKUP
                / path.relative_to(PROJECT)
            )

            backup_path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            shutil.copy2(
                path,
                backup_path,
            )

            backups[path] = backup_path

            write_text(
                path,
                patched,
            )

            changed.append(path)
            total_removed += removed

            print(
                f" - Đã ẩn {removed} mục tại "
                f"{path.relative_to(PROJECT)}"
            )

        if total_removed == 0:
            raise RuntimeError(
                "Có route cấu hình lớp nhưng không nhận diện được "
                "mục menu an toàn để xóa. Không thay đổi source."
            )

        verify_no_menu_link(
            changed
        )

        print()
        print("KIỂM TRA SAU CÀI:")
        print(
            " - 4.2.2. Cấu hình lớp: ĐÃ ẨN KHỎI MENU"
        )
        print(
            " - Route /doi-ngu/cau-hinh-lop: GIỮ NGUYÊN"
        )
        print(
            " - Database: KHÔNG THAY ĐỔI"
        )
        print(
            " - CSVC: KHÔNG THAY ĐỔI"
        )
        print()
        print(
            "Backup:",
            BACKUP,
        )
        print()
        print("=" * 122)
        print(
            "CÀI ĐẶT BÀI 13B-11.14.7.2.1 THÀNH CÔNG"
        )
        print("=" * 122)

        return 0

    except Exception:
        traceback.print_exc()

        print()
        print(
            "CÓ LỖI - ĐANG KHÔI PHỤC SOURCE..."
        )

        for path in changed:
            backup_path = backups.get(path)

            if (
                backup_path is not None
                and backup_path.exists()
            ):
                shutil.copy2(
                    backup_path,
                    path,
                )

                print(
                    " - Đã khôi phục:",
                    path.relative_to(PROJECT),
                )

        print(
            "Database không bị thay đổi."
        )

        print(
            "Backup:",
            BACKUP,
        )

        return 1


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
