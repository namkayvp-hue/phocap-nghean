# -*- coding: utf-8 -*-
# =============================================================================
# BÀI 13B-11.15.2.4.9.2A.1 V1
# CHUẨN HÓA CÁCH VIẾT TỶ LỆ - MN / TH / THCS
#
# YÊU CẦU:
# - Mầm non, Tiểu học, THCS:
#       100.00 / 100,00  -> 100%
# - Xóa mù chữ:
#       GIỮ NGUYÊN, vì đang hiển thị đúng.
#
# CHỈ THAY ĐỊNH DẠNG HIỂN THỊ:
# - Không đổi giá trị.
# - Không đổi công thức.
# - Không đổi kết luận.
# - Không đổi database.
# - Không đổi menu/route.
# =============================================================================

from __future__ import annotations

import ast
import hashlib
import os
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path


PROJECT = Path(
    os.environ.get(
        "PHOCAP_PROJECT",
        r"C:\PhoCap",
    )
).resolve()

APP = PROJECT / "app"
DB = PROJECT / "data" / "phocap.db"
EXPORTS = PROJECT / "exports"

MN_BUILDER = (
    APP
    / "pcgd_mn_report_builders_v1.py"
)

XMC_BUILDER = (
    APP
    / "pcgd_xmc_report_builders_v1.py"
)

EXPECTED_COMMUNES = 130
EXPECTED_SPECIAL = 51

STAMP = datetime.now().strftime(
    "%Y%m%d_%H%M%S"
)

BACKUP = (
    EXPORTS
    / (
        "backup_source_bai_13b_11_15_2_4_9_2a_1_"
        f"{STAMP}"
    )
)

REPORT = (
    EXPORTS
    / (
        "bao_cao_cai_dat_bai_13b_11_15_2_4_9_2a_1_"
        f"{STAMP}.txt"
    )
)

MN_HELPER_START = (
    "# === BAI_13B_11_15_2_4_9_2A_1_"
    "MN_HELPERS_START ==="
)
MN_HELPER_END = (
    "# === BAI_13B_11_15_2_4_9_2A_1_"
    "MN_HELPERS_END ==="
)
MN_CALL_START = (
    "# === BAI_13B_11_15_2_4_9_2A_1_"
    "MN_CALL_START ==="
)
MN_CALL_END = (
    "# === BAI_13B_11_15_2_4_9_2A_1_"
    "MN_CALL_END ==="
)

XMC_HELPER_START = (
    "# === BAI_13B_11_15_2_4_9_2A_1_"
    "XMC_HELPERS_START ==="
)
XMC_HELPER_END = (
    "# === BAI_13B_11_15_2_4_9_2A_1_"
    "XMC_HELPERS_END ==="
)
XMC_CALL_START = (
    "# === BAI_13B_11_15_2_4_9_2A_1_"
    "XMC_CALL_START ==="
)
XMC_CALL_END = (
    "# === BAI_13B_11_15_2_4_9_2A_1_"
    "XMC_CALL_END ==="
)

MN_HELPERS = '# === BAI_13B_11_15_2_4_9_2A_1_MN_HELPERS_START ===\ndef _b492a1_format_mn_percent_display(ws, report_type: str) -> None:\n    """\n    Chỉ chuẩn hóa CÁCH HIỂN THỊ phần trăm.\n    Giá trị vẫn là số 0..100; không đổi công thức, không đổi dữ liệu.\n    """\n    if report_type != "PCGD_MN_02_2025":\n        return\n\n    for ref in ("H7", "K7", "O7"):\n        ws[ref].number_format = r"0\\%"\n# === BAI_13B_11_15_2_4_9_2A_1_MN_HELPERS_END ==='
MN_CALL = '_b492a1_format_mn_percent_display(\n    ws,\n    report_type,\n)'
XMC_HELPERS = '# === BAI_13B_11_15_2_4_9_2A_1_XMC_HELPERS_START ===\ndef _b492a1_format_th_thcs_percent_display(ws, report_type: str) -> None:\n    """\n    Chuẩn hóa cách viết tỷ lệ cho TIỂU HỌC và THCS:\n        100 -> 100%\n\n    KHÔNG áp dụng cho Xóa mù chữ vì XMC hiện đã đúng.\n    KHÔNG thay đổi giá trị/công thức.\n    """\n    mappings = {\n        "PCGD_TH_02_2025": (\n            "I8",\n            "K8",\n            "M8",\n            "Q8",\n        ),\n        "PCGD_THCS_M1_2025": (\n            "H39",\n            "H40",\n            "H41",\n        ),\n        "PCGD_THCS_M2_2025": (\n            "E14",\n            "J14",\n            "M14",\n            "Q14",\n            "V14",\n            "E15",\n            "J15",\n            "M15",\n            "Q15",\n            "V15",\n            "K20",\n            "K21",\n            "K22",\n            "K23",\n            "K24",\n        ),\n        "PCGD_THCS_TK_2025": (\n            "I8",\n            "K8",\n            "O8",\n        ),\n    }\n\n    for ref in mappings.get(report_type, ()):\n        ws[ref].number_format = r"0\\%"\n# === BAI_13B_11_15_2_4_9_2A_1_XMC_HELPERS_END ==='
XMC_CALL = '_b492a1_format_th_thcs_percent_display(\n    ws,\n    report_type,\n)'


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


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()

    with path.open("rb") as f:
        for chunk in iter(
            lambda: f.read(
                1024 * 1024
            ),
            b"",
        ):
            h.update(chunk)

    return h.hexdigest()


def function_node(
    source: str,
    name: str,
):
    tree = ast.parse(source)

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
            f"Phải tìm thấy đúng 1 hàm {name}; "
            f"hiện có {len(matches)}."
        )

    return matches[0]


def get_function(
    source: str,
    name: str,
) -> str:
    node = function_node(
        source,
        name,
    )

    lines = source.splitlines(
        keepends=True
    )

    return "".join(
        lines[
            node.lineno - 1:
            node.end_lineno
        ]
    )


def replace_function(
    source: str,
    name: str,
    new_function: str,
) -> str:
    node = function_node(
        source,
        name,
    )

    lines = source.splitlines(
        keepends=True
    )

    before = "".join(
        lines[
            :node.lineno - 1
        ]
    )

    after = "".join(
        lines[
            node.end_lineno:
        ]
    )

    result = (
        before
        + new_function.rstrip()
        + "\n\n"
        + after.lstrip("\n")
    )

    ast.parse(result)

    return result


def indent_block(
    block: str,
    indent: str,
) -> str:
    return "\n".join(
        (
            indent + row
            if row.strip()
            else ""
        )
        for row in block.splitlines()
    )


def append_block(
    source: str,
    *,
    start_marker: str,
    end_marker: str,
    block: str,
) -> str:
    has_start = (
        start_marker
        in source
    )
    has_end = (
        end_marker
        in source
    )

    if has_start and has_end:
        return source

    if has_start != has_end:
        raise RuntimeError(
            "Marker helper dở dang: "
            + start_marker
        )

    result = (
        source.rstrip()
        + "\n\n"
        + block.rstrip()
        + "\n"
    )

    ast.parse(result)

    return result


def insert_call_before_save(
    source: str,
    *,
    function_name: str,
    start_marker: str,
    end_marker: str,
    call_block: str,
) -> str:
    function = get_function(
        source,
        function_name,
    )

    has_start = (
        start_marker
        in function
    )
    has_end = (
        end_marker
        in function
    )

    if has_start and has_end:
        return source

    if has_start != has_end:
        raise RuntimeError(
            "Marker call dở dang trong "
            + function_name
        )

    lines = function.splitlines(
        keepends=True
    )

    indexes = [
        index
        for index, line in enumerate(
            lines
        )
        if "workbook.save(output)" in line
    ]

    if len(indexes) != 1:
        raise RuntimeError(
            f"{function_name}: phải có đúng 1 "
            "workbook.save(output); "
            f"hiện có {len(indexes)}."
        )

    index = indexes[0]
    save_line = lines[index]

    indent = save_line[
        :len(save_line)
        - len(
            save_line.lstrip()
        )
    ]

    payload = (
        indent
        + start_marker
        + "\n"
        + indent_block(
            call_block,
            indent,
        )
        + "\n"
        + indent
        + end_marker
        + "\n"
    )

    lines.insert(
        index,
        payload,
    )

    new_function = "".join(
        lines
    )

    return replace_function(
        source,
        function_name,
        new_function,
    )


def db_state() -> dict:
    uri = (
        DB.resolve().as_uri()
        + "?mode=ro"
    )

    con = sqlite3.connect(
        uri,
        uri=True,
    )

    try:
        integrity = str(
            con.execute(
                "PRAGMA integrity_check"
            ).fetchone()[0]
        )

        fk = len(
            con.execute(
                "PRAGMA foreign_key_check"
            ).fetchall()
        )

        total = int(
            con.execute(
                "SELECT COUNT(*) "
                "FROM communes"
            ).fetchone()[0]
        )

        special = int(
            con.execute(
                """
                SELECT COUNT(*)
                FROM communes
                WHERE COALESCE(
                    is_special_difficulty_area,
                    0
                ) = 1
                """
            ).fetchone()[0]
        )

        return {
            "integrity": integrity,
            "fk": fk,
            "total": total,
            "special": special,
        }

    finally:
        con.close()


def verify_db(
    state: dict,
) -> None:
    if str(
        state["integrity"]
    ).lower() != "ok":
        raise RuntimeError(
            "integrity_check != ok"
        )

    if int(
        state["fk"]
    ) != 0:
        raise RuntimeError(
            "foreign_key_check có lỗi."
        )

    if int(
        state["total"]
    ) != EXPECTED_COMMUNES:
        raise RuntimeError(
            f"communes={state['total']}, "
            f"không phải {EXPECTED_COMMUNES}."
        )

    if int(
        state["special"]
    ) != EXPECTED_SPECIAL:
        raise RuntimeError(
            f"ĐBKK={state['special']}, "
            f"không phải {EXPECTED_SPECIAL}."
        )


def verify_base() -> None:
    mn = read_text(
        MN_BUILDER
    )

    xmc = read_text(
        XMC_BUILDER
    )

    required_mn = (
        "BAI_13B_11_15_2_4_9_1_"
        "MN_HELPERS_START",
        "BAI_13B_11_15_2_4_9_2_"
        "MN_HELPERS_START",
        "def export_mn_report(",
    )

    required_xmc = (
        "BAI_13B_11_15_2_4_9_1_"
        "XMC_HELPERS_START",
        "BAI_13B_11_15_2_4_9_2_"
        "XMC_HELPERS_START",
        "def export_additional_report(",
    )

    missing = (
        [
            "MN:" + token
            for token in required_mn
            if token not in mn
        ]
        + [
            "XMC:" + token
            for token in required_xmc
            if token not in xmc
        ]
    )

    if missing:
        raise RuntimeError(
            "Source chưa đúng nền "
            "Bài 4.9.1/4.9.2: "
            + "; ".join(missing)
        )


def backup_sources() -> None:
    for path in (
        MN_BUILDER,
        XMC_BUILDER,
    ):
        dst = (
            BACKUP
            / path.relative_to(
                PROJECT
            )
        )

        dst.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        shutil.copy2(
            path,
            dst,
        )


def restore_sources() -> None:
    for path in (
        MN_BUILDER,
        XMC_BUILDER,
    ):
        src = (
            BACKUP
            / path.relative_to(
                PROJECT
            )
        )

        if src.exists():
            shutil.copy2(
                src,
                path,
            )


def patch_sources() -> None:
    mn = append_block(
        read_text(
            MN_BUILDER
        ),
        start_marker=(
            MN_HELPER_START
        ),
        end_marker=(
            MN_HELPER_END
        ),
        block=MN_HELPERS,
    )

    mn = insert_call_before_save(
        mn,
        function_name=(
            "export_mn_report"
        ),
        start_marker=(
            MN_CALL_START
        ),
        end_marker=(
            MN_CALL_END
        ),
        call_block=MN_CALL,
    )

    xmc = append_block(
        read_text(
            XMC_BUILDER
        ),
        start_marker=(
            XMC_HELPER_START
        ),
        end_marker=(
            XMC_HELPER_END
        ),
        block=XMC_HELPERS,
    )

    xmc = insert_call_before_save(
        xmc,
        function_name=(
            "export_additional_report"
        ),
        start_marker=(
            XMC_CALL_START
        ),
        end_marker=(
            XMC_CALL_END
        ),
        call_block=XMC_CALL,
    )

    ast.parse(mn)
    ast.parse(xmc)

    write_text(
        MN_BUILDER,
        mn,
    )

    write_text(
        XMC_BUILDER,
        xmc,
    )


def verify_installed() -> None:
    mn = read_text(
        MN_BUILDER
    )
    xmc = read_text(
        XMC_BUILDER
    )

    ast.parse(mn)
    ast.parse(xmc)

    for token in (
        MN_HELPER_START,
        MN_HELPER_END,
        MN_CALL_START,
        MN_CALL_END,
        "def _b492a1_format_mn_percent_display(",
        '"H7"',
        '"K7"',
        '"O7"',
    ):
        if token not in mn:
            raise RuntimeError(
                "Verifier MN thiếu: "
                + token
            )

    for token in (
        XMC_HELPER_START,
        XMC_HELPER_END,
        XMC_CALL_START,
        XMC_CALL_END,
        "def _b492a1_format_th_thcs_percent_display(",
        '"PCGD_TH_02_2025"',
        '"PCGD_THCS_M1_2025"',
        '"PCGD_THCS_M2_2025"',
        '"PCGD_THCS_TK_2025"',
    ):
        if token not in xmc:
            raise RuntimeError(
                "Verifier TH/THCS thiếu: "
                + token
            )

    # Khóa chính xác number_format trong helper.
    mn_helper = get_function(
        mn,
        "_b492a1_format_mn_percent_display",
    )

    xmc_helper = get_function(
        xmc,
        "_b492a1_format_th_thcs_percent_display",
    )

    if (
        'number_format = r"0\\%"'
        not in mn_helper
    ):
        raise RuntimeError(
            "Formatter MN chưa dùng 0\\%."
        )

    if (
        'number_format = r"0\\%"'
        not in xmc_helper
    ):
        raise RuntimeError(
            "Formatter TH/THCS chưa dùng 0\\%."
        )

    if (
        '"PCGD_XMC_4_2025"'
        in xmc_helper
    ):
        raise RuntimeError(
            "Không được đổi định dạng XMC-4."
        )

    mn_export = get_function(
        mn,
        "export_mn_report",
    )

    xmc_export = get_function(
        xmc,
        "export_additional_report",
    )

    if (
        mn_export.find(
            MN_CALL_START
        )
        < 0
        or mn_export.find(
            MN_CALL_START
        )
        >= mn_export.find(
            "workbook.save(output)"
        )
    ):
        raise RuntimeError(
            "Call format MN chưa đứng "
            "trước workbook.save."
        )

    if (
        xmc_export.find(
            XMC_CALL_START
        )
        < 0
        or xmc_export.find(
            XMC_CALL_START
        )
        >= xmc_export.find(
            "workbook.save(output)"
        )
    ):
        raise RuntimeError(
            "Call format TH/THCS chưa đứng "
            "trước workbook.save."
        )

    for path in (
        MN_BUILDER,
        XMC_BUILDER,
    ):
        subprocess.run(
            [
                sys.executable,
                "-m",
                "py_compile",
                str(path),
            ],
            cwd=str(PROJECT),
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
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


def all_markers_present() -> bool:
    mn = read_text(
        MN_BUILDER
    )
    xmc = read_text(
        XMC_BUILDER
    )

    return (
        all(
            marker in mn
            for marker in (
                MN_HELPER_START,
                MN_HELPER_END,
                MN_CALL_START,
                MN_CALL_END,
            )
        )
        and all(
            marker in xmc
            for marker in (
                XMC_HELPER_START,
                XMC_HELPER_END,
                XMC_CALL_START,
                XMC_CALL_END,
            )
        )
    )


def any_marker_present() -> bool:
    text = (
        read_text(
            MN_BUILDER
        )
        + "\n"
        + read_text(
            XMC_BUILDER
        )
    )

    return any(
        marker in text
        for marker in (
            MN_HELPER_START,
            MN_HELPER_END,
            MN_CALL_START,
            MN_CALL_END,
            XMC_HELPER_START,
            XMC_HELPER_END,
            XMC_CALL_START,
            XMC_CALL_END,
        )
    )


def main() -> int:
    print("=" * 104)
    print(
        "BÀI 13B-11.15.2.4.9.2A.1 V1 - "
        "CHUẨN HÓA CÁCH VIẾT TỶ LỆ"
    )
    print("=" * 104)
    print()

    backup_created = False

    try:
        for path in (
            DB,
            MN_BUILDER,
            XMC_BUILDER,
        ):
            if not path.exists():
                raise RuntimeError(
                    f"Không tìm thấy: {path}"
                )

        db_hash_before = (
            sha256_file(DB)
        )

        print(
            "[1/7] Kiểm tra database..."
        )

        before = db_state()
        verify_db(
            before
        )

        print(
            "[OK] "
            f"{before['total']} xã/phường; "
            f"ĐBKK={before['special']}; "
            "integrity=ok."
        )

        print(
            "[2/7] Kiểm tra nền "
            "Bài 4.9.1 + 4.9.2..."
        )

        verify_base()

        print(
            "[OK] Đúng nền."
        )

        if all_markers_present():
            print(
                "[3/7] Bài 4.9.2A.1 "
                "đã có marker đầy đủ."
            )

            print(
                "[4/7] Không sửa source lặp."
            )

        else:
            if any_marker_present():
                raise RuntimeError(
                    "Marker 4.9.2A.1 "
                    "đang dở dang. "
                    "Dừng để tránh sửa chồng."
                )

            print(
                "[3/7] Backup source..."
            )

            BACKUP.mkdir(
                parents=True,
                exist_ok=False,
            )

            backup_created = True

            backup_sources()

            print(
                f"[OK] {BACKUP}"
            )

            print(
                "[4/7] Cài định dạng "
                "MN / TH / THCS..."
            )

            patch_sources()

            print(
                "[OK] Đã nối formatter."
            )

        print(
            "[5/7] AST + py_compile "
            "+ verifier..."
        )

        verify_installed()

        print(
            "[OK] Đạt."
        )

        print(
            "[6/7] Kiểm tra database "
            "sau cài..."
        )

        after = db_state()
        verify_db(
            after
        )

        db_hash_after = (
            sha256_file(DB)
        )

        if (
            db_hash_after
            != db_hash_before
        ):
            raise RuntimeError(
                "SHA256 phocap.db thay đổi. "
                "Bài này không được phép sửa DB."
            )

        print(
            "[OK] Database KHÔNG THAY ĐỔI; "
            "SHA256 giữ nguyên."
        )

        print(
            "[7/7] Ghi báo cáo..."
        )

        EXPORTS.mkdir(
            parents=True,
            exist_ok=True,
        )

        lines = [
            "=" * 104,
            "BÀI 13B-11.15.2.4.9.2A.1 V1 - "
            "BÁO CÁO CÀI ĐẶT",
            "=" * 104,
            "",
            "YÊU CẦU ĐÃ CÀI:",
            " - Mầm non: tỷ lệ hiển thị dạng 100%.",
            " - Tiểu học: tỷ lệ hiển thị dạng 100%.",
            " - THCS: tỷ lệ hiển thị dạng 100%.",
            " - Xóa mù chữ: GIỮ NGUYÊN.",
            "",
            "ĐỊNH DẠNG:",
            r" - Excel number_format = 0\%",
            " - Chỉ thay cách hiển thị.",
            " - Không thay giá trị/công thức.",
            "",
            "MẦM NON:",
            " - MN-02: H7, K7, O7",
            "",
            "TIỂU HỌC:",
            " - TH-02: I8, K8, M8, Q8",
            "",
            "THCS:",
            " - THCS-M1: H39:H41",
            " - THCS-M2: E/J/M/Q/V hàng 14-15; K20:K24",
            " - THCS-TK: I8, K8, O8",
            "",
            "XMC:",
            " - XMC-4 không có trong mapping.",
            " - Định dạng hiện hành được giữ nguyên.",
            "",
            f"DB SHA256 trước: {db_hash_before}",
            f"DB SHA256 sau  : {db_hash_after}",
            "Database: KHÔNG THAY ĐỔI.",
            "",
            (
                f"Backup source: {BACKUP}"
                if backup_created
                else "Source đã có Bài 4.9.2A.1 từ trước."
            ),
            "",
            "AST + py_compile: ĐẠT.",
            "KẾT LUẬN: CÀI ĐẶT THÀNH CÔNG.",
        ]

        REPORT.write_text(
            "\n".join(lines),
            encoding="utf-8-sig",
        )

        clear_cache()

        print(
            f"[OK] {REPORT}"
        )

        print()
        print("=" * 104)
        print(
            "BÀI 4.9.2A.1 V1 HOÀN THÀNH."
        )
        print("=" * 104)
        print(
            "MN / TH / THCS : 100 -> 100%"
        )
        print(
            "XMC            : GIỮ NGUYÊN"
        )
        print(
            "Database       : KHÔNG THAY ĐỔI"
        )
        print(
            f"Báo cáo        : {REPORT}"
        )
        print("=" * 104)

        return 0

    except Exception as exc:
        print()
        print("=" * 104)
        print(
            "[LỖI] BÀI 4.9.2A.1 "
            "KHÔNG HOÀN THÀNH"
        )
        print(str(exc))
        print("=" * 104)

        if backup_created:
            try:
                restore_sources()
                clear_cache()

                print(
                    "[ROLLBACK] Đã khôi phục "
                    "2 source từ backup."
                )

            except Exception as rollback_exc:
                print(
                    "[CẢNH BÁO] Rollback lỗi: "
                    + str(rollback_exc)
                )

        print(
            "Bài này không có lệnh "
            "UPDATE/INSERT/DELETE database."
        )

        return 1


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
