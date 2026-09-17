from __future__ import annotations

import ast
import os
import shutil
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

TARGET = (
    PROJECT
    / "app"
    / "routers"
    / "surveys.py"
)

STAMP = datetime.now().strftime(
    "%Y%m%d_%H%M%S"
)

BACKUP = (
    PROJECT
    / "exports"
    / f"backup_bai_13b_11_13_3_3_{STAMP}"
)

OLD_CALL = (
    "completion_data = "
    "b131133_danh_gia_do_day_du_phieu_nhap_nhanh("
)

NEW_CALL = (
    "completion_data = "
    "danh_gia_do_day_du_phieu_nhap_nhanh("
)

MARKER = (
    "# === "
    "BAI_13B_11_13_3_3_FIX_QUICK_ENTRY_PEOPLE"
    " ==="
)


def read_text(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(
            f"Không tìm thấy: {path}"
        )

    return path.read_text(
        encoding="utf-8-sig"
    )


def write_text(
    path: Path,
    text: str,
) -> None:
    path.write_text(
        text,
        encoding="utf-8",
    )


def backup_source() -> None:
    dst = (
        BACKUP
        / TARGET.relative_to(PROJECT)
    )

    dst.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    shutil.copy2(
        TARGET,
        dst,
    )


def restore_source() -> None:
    src = (
        BACKUP
        / TARGET.relative_to(PROJECT)
    )

    if src.exists():
        shutil.copy2(
            src,
            TARGET,
        )


def find_top_function(
    tree: ast.Module,
    name: str,
):
    found = [
        node
        for node in tree.body
        if isinstance(
            node,
            (
                ast.FunctionDef,
                ast.AsyncFunctionDef,
            ),
        )
        and node.name == name
    ]

    if len(found) != 1:
        raise RuntimeError(
            f"Phải tìm thấy đúng 1 hàm {name}; "
            f"hiện có {len(found)}."
        )

    return found[0]


def patch(text: str) -> str:
    if MARKER in text:
        print(
            " - Bài 13B-11.13.3.3 "
            "đã có sẵn; không sửa lặp."
        )
        return text

    if (
        "def b131133_danh_gia_do_day_du_phieu_nhap_nhanh"
        not in text
    ):
        raise RuntimeError(
            "Không thấy helper động của "
            "Bài 13B-11.13.3.2."
        )

    tree = ast.parse(
        text
    )

    fn = find_top_function(
        tree,
        "hien_thi_trang_nhap_nhanh",
    )

    lines = text.splitlines(
        keepends=True
    )

    start = int(fn.lineno) - 1
    end = int(fn.end_lineno)

    segment = "".join(
        lines[start:end]
    )

    old_count = segment.count(
        OLD_CALL
    )

    new_count = segment.count(
        NEW_CALL
    )

    if old_count == 0 and new_count == 1:
        # Có thể source đã được sửa tay đúng logic,
        # chỉ chèn marker xác nhận.
        body_line = int(
            fn.body[0].lineno
        ) - 1

        indent = lines[
            body_line
        ][
            : len(lines[body_line])
            - len(lines[body_line].lstrip())
        ]

        lines.insert(
            body_line,
            indent + MARKER + "\n",
        )

        patched = "".join(
            lines
        )

        ast.parse(
            patched
        )

        return patched

    if old_count != 1:
        raise RuntimeError(
            "Trong hien_thi_trang_nhap_nhanh "
            "phải có đúng 1 lời gọi helper động; "
            f"hiện có {old_count}."
        )

    segment = segment.replace(
        OLD_CALL,
        NEW_CALL,
        1,
    )

    # Chèn marker ngay trước lời gọi vừa sửa.
    call_pos = segment.find(
        NEW_CALL
    )

    if call_pos < 0:
        raise RuntimeError(
            "Không tìm thấy lời gọi helper "
            "sau khi thay thế."
        )

    line_start = segment.rfind(
        "\n",
        0,
        call_pos,
    ) + 1

    call_line = segment[
        line_start:
        segment.find(
            "\n",
            call_pos,
        )
    ]

    indent = call_line[
        : len(call_line)
        - len(call_line.lstrip())
    ]

    segment = (
        segment[:line_start]
        + indent
        + MARKER
        + "\n"
        + segment[line_start:]
    )

    lines[start:end] = [
        segment
    ]

    patched = "".join(
        lines
    )

    ast.parse(
        patched
    )

    return patched


def verify(
    text: str,
) -> None:
    if MARKER not in text:
        raise RuntimeError(
            "Thiếu marker sửa lỗi "
            "13B-11.13.3.3."
        )

    tree = ast.parse(
        text
    )

    fn = find_top_function(
        tree,
        "hien_thi_trang_nhap_nhanh",
    )

    lines = text.splitlines(
        keepends=True
    )

    segment = "".join(
        lines[
            int(fn.lineno) - 1
            :
            int(fn.end_lineno)
        ]
    )

    if OLD_CALL in segment:
        raise RuntimeError(
            "Màn Nhập nhanh vẫn còn dùng "
            "helper động thiếu khóa people."
        )

    if segment.count(
        NEW_CALL
    ) != 1:
        raise RuntimeError(
            "Màn Nhập nhanh không có đúng "
            "1 helper đầy đủ cũ."
        )

    # Hai luồng POST kiểm tra hoàn thành vẫn phải
    # giữ helper động. Toàn file phải còn ít nhất 2.
    dynamic_count = text.count(
        OLD_CALL
    )

    if dynamic_count < 2:
        raise RuntimeError(
            "Số lời gọi helper động toàn file "
            f"còn {dynamic_count}; dự kiến ít nhất 2 "
            "cho các luồng kiểm tra hoàn thành."
        )

    # Kiểm tra đoạn gây lỗi vẫn đang dùng people,
    # và giờ helper cung cấp cấu trúc tương thích.
    if 'completion_data["people"]' not in segment:
        print(
            " - Lưu ý: source hiện tại không còn "
            'completion_data["people"]; vẫn chấp nhận.'
        )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "py_compile",
            str(TARGET),
        ],
        cwd=PROJECT,
        text=True,
        capture_output=True,
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
            "py_compile surveys.py không đạt."
        )


def clear_cache() -> None:
    app_dir = PROJECT / "app"

    for cache in app_dir.rglob(
        "__pycache__"
    ):
        if cache.is_dir():
            shutil.rmtree(
                cache,
                ignore_errors=True,
            )


def main() -> int:
    print("=" * 122)
    print(
        "BÀI 13B-11.13.3.3 - "
        "SỬA LỖI 500 NHẬP NHANH KEYERROR 'people'"
    )
    print("=" * 122)
    print()
    print("NGUYÊN NHÂN:")
    print(
        " - Màn Nhập nhanh cần completion_data['people']."
    )
    print(
        " - Helper động 13B-11.13.3.2 chỉ trả các số đếm."
    )
    print(
        " - Vì vậy GET /nhap-nhanh phát sinh KeyError: 'people'."
    )
    print()
    print("CÁCH SỬA:")
    print(
        " - Riêng hien_thi_trang_nhap_nhanh dùng lại "
        "danh_gia_do_day_du_phieu_nhap_nhanh."
    )
    print(
        " - Hai luồng kiểm tra Hoàn thành phiếu vẫn giữ "
        "b131133_danh_gia_do_day_du_phieu_nhap_nhanh."
    )
    print(
        " - Không bỏ logic tiến độ động theo MN/TH/THCS/XMC."
    )
    print()
    print("AN TOÀN:")
    print(
        " - Chỉ sửa app/routers/surveys.py."
    )
    print(
        " - Không sửa database."
    )
    print(
        " - Không sửa model/template."
    )
    print(
        " - Có backup và tự rollback nếu lỗi."
    )
    print()

    BACKUP.mkdir(
        parents=True,
        exist_ok=False,
    )

    backup_source()

    print(
        "Backup:",
        BACKUP,
    )

    try:
        before = read_text(
            TARGET
        )

        after = patch(
            before
        )

        verify(
            after
        )

        write_text(
            TARGET,
            after,
        )

        # compile lại file thực tế sau khi ghi
        verify(
            read_text(
                TARGET
            )
        )

        clear_cache()

        print()
        print("KIỂM TRA SAU CÀI:")
        print(
            " - Nhập nhanh dùng helper có people: OK"
        )
        print(
            " - Hai luồng hoàn thành vẫn dùng helper động: OK"
        )
        print(
            " - py_compile surveys.py: OK"
        )
        print(
            " - Database: KHÔNG THAY ĐỔI"
        )
        print()
        print(
            "CÀI ĐẶT BÀI "
            "13B-11.13.3.3 THÀNH CÔNG"
        )

        return 0

    except Exception:
        traceback.print_exc()

        print()
        print(
            "CÓ LỖI - "
            "ĐANG KHÔI PHỤC surveys.py..."
        )

        restore_source()
        clear_cache()

        print(
            "ĐÃ KHÔI PHỤC SOURCE."
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
