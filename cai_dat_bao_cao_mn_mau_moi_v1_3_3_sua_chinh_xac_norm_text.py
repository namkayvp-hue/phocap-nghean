from __future__ import annotations

import ast
import os
import re
import shutil
import sqlite3
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

APP = PROJECT / "app"
ROUTER = APP / "routers" / "mn_official_reports.py"
DB = PROJECT / "data" / "phocap.db"

STAMP = datetime.now().strftime(
    "%Y%m%d_%H%M%S"
)

BACKUP = (
    PROJECT
    / "exports"
    / f"backup_bao_cao_mn_ty_le_v1_3_3_{STAMP}"
)

V13_START = (
    "# === "
    "BAO_CAO_MN_MAU_MOI_V1_3_TY_LE_TRUC_TIEP START"
    " ==="
)

V13_END = (
    "# === "
    "BAO_CAO_MN_MAU_MOI_V1_3_TY_LE_TRUC_TIEP END"
    " ==="
)

FIX_MARKER = (
    "# === "
    "BAO_CAO_MN_MAU_MOI_V1_3_2_FIX_NORM_TEXT"
    " ==="
)

HELPER = '\n    # === BAO_CAO_MN_MAU_MOI_V1_3_2_FIX_NORM_TEXT ===\n    def _v13_norm_text(value):\n        import unicodedata\n\n        text_value = str(\n            value or ""\n        )\n\n        text_value = unicodedata.normalize(\n            "NFD",\n            text_value,\n        )\n\n        text_value = "".join(\n            char\n            for char in text_value\n            if unicodedata.category(char) != "Mn"\n        )\n\n        return " ".join(\n            text_value.upper().split()\n        )\n'


def read_text(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(
            f"Không tìm thấy: {path}"
        )

    return path.read_text(
        encoding="utf-8-sig",
        errors="strict",
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
    target = (
        BACKUP
        / ROUTER.relative_to(PROJECT)
    )

    target.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    shutil.copy2(
        ROUTER,
        target,
    )


def restore_source() -> None:
    source = (
        BACKUP
        / ROUTER.relative_to(PROJECT)
    )

    if source.exists():
        shutil.copy2(
            source,
            ROUTER,
        )


def clear_cache() -> None:
    for cache in APP.rglob(
        "__pycache__"
    ):
        if cache.is_dir():
            shutil.rmtree(
                cache,
                ignore_errors=True,
            )


def db_check() -> tuple[str, int]:
    if not DB.exists():
        raise RuntimeError(
            f"Không tìm thấy database: {DB}"
        )

    conn = sqlite3.connect(
        str(DB)
    )

    try:
        integrity = str(
            conn.execute(
                "PRAGMA integrity_check"
            ).fetchone()[0]
        )

        fk_count = len(
            conn.execute(
                "PRAGMA foreign_key_check"
            ).fetchall()
        )

        return (
            integrity,
            fk_count,
        )

    finally:
        conn.close()


def function_span(
    source: str,
    name: str,
) -> tuple[int, int]:
    tree = ast.parse(
        source
    )

    matches = [
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

    if len(matches) != 1:
        raise RuntimeError(
            f"Phải tìm thấy đúng 1 hàm "
            f"{name}; hiện có {len(matches)}."
        )

    node = matches[0]

    lines = source.splitlines(
        keepends=True
    )

    offsets = [0]

    for line in lines:
        offsets.append(
            offsets[-1]
            + len(line)
        )

    return (
        offsets[
            int(node.lineno) - 1
        ],
        offsets[
            int(node.end_lineno)
        ],
    )


def patch_source(
    source: str,
) -> str:
    if V13_START not in source:
        raise RuntimeError(
            "Không thấy block V1.3 tính tỷ lệ trực tiếp. "
            "Source hiện tại không đúng nền cần sửa."
        )

    start, end = function_span(
        source,
        "_fill_te_workbook",
    )

    function_text = source[
        start:end
    ]

    block_start = function_text.find(
        V13_START
    )

    block_end = function_text.find(
        V13_END,
        block_start,
    )

    if (
        block_start < 0
        or block_end < 0
    ):
        raise RuntimeError(
            "Không xác định được đầy đủ "
            "block V1.3 trong _fill_te_workbook."
        )

    block_end += len(
        V13_END
    )

    block = function_text[
        block_start:block_end
    ]

    if FIX_MARKER not in block:
        anchor = "    def _v13_row_contains("

        anchor_pos = block.find(
            anchor
        )

        if anchor_pos < 0:
            raise RuntimeError(
                "Không tìm thấy "
                "def _v13_row_contains trong block V1.3."
            )

        block = (
            block[:anchor_pos]
            + HELPER.strip("\n")
            + "\n\n"
            + block[anchor_pos:]
        )

    # V1.3.3:
    # Chỉ thay lời gọi _norm_text(...) độc lập.
    # Không được nhầm phần "_norm_text(" nằm bên trong
    # tên hàm mới "_v13_norm_text(".
    standalone_pattern = re.compile(
        r"(?<![A-Za-z0-9_])_norm_text\("
    )

    block, replace_count = standalone_pattern.subn(
        "_v13_norm_text(",
        block,
    )

    if standalone_pattern.search(block):
        raise RuntimeError(
            "Block V1.3 vẫn còn lời gọi "
            "_norm_text độc lập chưa được thay thế."
        )

    print(
        " - Số lời gọi _norm_text độc lập đã thay:",
        replace_count,
    )

    new_function = (
        function_text[:block_start]
        + block
        + function_text[block_end:]
    )

    patched = (
        source[:start]
        + new_function
        + source[end:]
    )

    ast.parse(
        patched
    )

    return patched


def verify_source(
    source: str,
) -> None:
    ast.parse(
        source
    )

    start, end = function_span(
        source,
        "_fill_te_workbook",
    )

    function_text = source[
        start:end
    ]

    block_start = function_text.find(
        V13_START
    )

    block_end = function_text.find(
        V13_END,
        block_start,
    )

    if (
        block_start < 0
        or block_end < 0
    ):
        raise RuntimeError(
            "Không thấy block V1.3 "
            "sau khi cài."
        )

    block = function_text[
        block_start:
        block_end
        + len(V13_END)
    ]

    required = (
        FIX_MARKER,
        "def _v13_norm_text(value):",
        "_v13_norm_text(part)",
        "_v13_norm_text(row_text)",
        "_v13_norm_text(label)",
        "_v13_norm_text(value or \"\")",
        "def _v13_row_contains(",
        "def _v13_header_column(",
    )

    for item in required:
        if item not in block:
            raise RuntimeError(
                "Block V1.3.2 thiếu: "
                + item
            )

    standalone_pattern = re.compile(
        r"(?<![A-Za-z0-9_])_norm_text\("
    )

    if standalone_pattern.search(block):
        raise RuntimeError(
            "Block V1.3 vẫn còn gọi "
            "_norm_text cũ."
        )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "py_compile",
            str(ROUTER),
        ],
        cwd=PROJECT,
        capture_output=True,
        text=True,
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
            "py_compile mn_official_reports.py "
            "không đạt."
        )


def main() -> int:
    print("=" * 118)
    print(
        "BÁO CÁO MẦM NON V1.3.3 - "
        "SỬA LỖI 500 XUẤT MN-01-TE: "
        "NameError _norm_text"
    )
    print("=" * 118)
    print()
    print("LỖI BỘ CÀI V1.3.2 ĐÃ XÁC ĐỊNH:")
    print(
        " - V1.3.2 kiểm tra bằng chuỗi '_norm_text('."
    )
    print(
        " - Chuỗi này cũng nằm trong tên '_v13_norm_text(', "
        "nên bị nhận nhầm là còn lỗi."
    )
    print(
        " - V1.3.3 dùng regex chỉ bắt _norm_text(...) độc lập."
    )
    print()
    print("LỖI RUNTIME BAN ĐẦU:")
    print(
        " - _fill_te_workbook -> "
        "_v13_row_contains -> _norm_text(part)"
    )
    print(
        " - NameError: name '_norm_text' is not defined"
    )
    print()
    print("CÁCH SỬA:")
    print(
        " - Tạo _v13_norm_text() riêng "
        "ngay trong block V1.3."
    )
    print(
        " - Thay toàn bộ _norm_text() của V1.3 "
        "bằng _v13_norm_text()."
    )
    print(
        " - Giữ nguyên toàn bộ logic tỷ lệ V1.3."
    )
    print()
    print("AN TOÀN:")
    print(
        " - Chỉ sửa app/routers/"
        "mn_official_reports.py."
    )
    print(
        " - Không sửa database."
    )
    print(
        " - Không sửa mẫu Excel gốc."
    )
    print(
        " - Có backup và rollback nếu lỗi."
    )
    print()

    if not ROUTER.exists():
        raise RuntimeError(
            f"Không tìm thấy: {ROUTER}"
        )

    (
        integrity_before,
        fk_before,
    ) = db_check()

    print(
        "integrity_check trước cài:",
        integrity_before,
    )
    print(
        "foreign_key_check trước cài:",
        fk_before,
        "lỗi",
    )

    if (
        integrity_before.lower()
        != "ok"
        or fk_before != 0
    ):
        raise RuntimeError(
            "Database không đạt kiểm tra "
            "an toàn trước khi cài."
        )

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
        original = read_text(
            ROUTER
        )

        patched = patch_source(
            original
        )

        verify_source(
            patched
        )

        write_text(
            ROUTER,
            patched,
        )

        verify_source(
            read_text(
                ROUTER
            )
        )

        clear_cache()

        (
            integrity_after,
            fk_after,
        ) = db_check()

        if (
            integrity_after.lower()
            != "ok"
            or fk_after != 0
        ):
            raise RuntimeError(
                "Database không đạt "
                "kiểm tra sau cài."
            )

        print()
        print("KIỂM TRA SAU CÀI:")
        print(
            " - _v13_norm_text: OK"
        )
        print(
            " - Không còn _norm_text trong block V1.3: OK"
        )
        print(
            " - Logic tỷ lệ V1.3: GIỮ NGUYÊN"
        )
        print(
            " - py_compile: OK"
        )
        print(
            " - Database: KHÔNG THAY ĐỔI"
        )
        print(
            " - Mẫu Excel gốc: KHÔNG THAY ĐỔI"
        )
        print(
            " - integrity_check:",
            integrity_after,
        )
        print(
            " - foreign_key_check:",
            fk_after,
            "lỗi",
        )
        print()
        print("=" * 118)
        print(
            "CÀI ĐẶT BÁO CÁO "
            "MẦM NON V1.3.2 THÀNH CÔNG"
        )
        print("=" * 118)

        return 0

    except Exception:
        traceback.print_exc()

        print()
        print(
            "CÓ LỖI - "
            "ĐANG KHÔI PHỤC SOURCE..."
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
