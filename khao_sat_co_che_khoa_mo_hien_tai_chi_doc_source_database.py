# -*- coding: utf-8 -*-
"""
KHẢO SÁT TRẠNG THÁI HIỆN TẠI CỦA TOÀN BỘ CƠ CHẾ KHÓA / MỞ
====================================================================

MỤC TIÊU
--------
Chỉ đọc SOURCE + DATABASE hiện tại trước khi kiểm thử khóa/mở thực tế.

KHÔNG THỰC HIỆN:
- Không sửa source.
- Không UPDATE / INSERT / DELETE database.
- Không gọi route khóa/mở.
- Không thay đổi trạng thái đợt / xã / trường.
- Không xóa cache.
- Không restart ứng dụng.

CHỈ THỰC HIỆN:
1. SHA256 source + database trước/sau.
2. AST parse các source chính.
3. Khảo sát AccessControlMiddleware.
4. Khảo sát survey_school_workflow.py:
   - khóa/mở trường
   - khóa/mở toàn xã
   - khóa/mở toàn tỉnh
   - trạng thái địa bàn
   - đồng bộ khóa về SurveyBatch
5. Khảo sát surveys.py và các route ghi.
6. Khảo sát template có nút khóa/mở.
7. Đọc schema SQLite bằng mode=ro + query_only.
8. Thống kê trạng thái khóa thực tế đang lưu trong database.
9. Phát hiện nhật ký khóa/mở.
10. Lập ma trận hiện trạng và các điểm cần kiểm thử tiếp theo.

Kết quả chỉ được ghi vào một file TXT trong C:\\PhoCap\\exports.
"""

from __future__ import annotations

import ast
import hashlib
import os
import re
import sqlite3
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT = Path(
    os.environ.get(
        "PHOCAP_PROJECT",
        r"C:\PhoCap",
    )
).resolve()

APP = PROJECT / "app"
DB = PROJECT / "data" / "phocap.db"
EXPORTS = PROJECT / "exports"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

REPORT = (
    EXPORTS
    / (
        "khao_sat_co_che_khoa_mo_"
        f"hien_tai_{STAMP}.txt"
    )
)

SOURCE_TARGETS = (
    APP / "access_control.py",
    APP / "models.py",
    APP / "routers" / "surveys.py",
    APP / "routers" / "survey_school_workflow.py",
)

OPTIONAL_SOURCE_TARGETS = (
    APP / "main.py",
    APP / "__init__.py",
)

WORKFLOW_FUNCTIONS = (
    "lay_trang_thai_dia_ban",
    "dong_bo_khoa_dot",
    "khoa_truong",
    "mo_khoa_truong",
    "yeu_cau_bo_sung",
    "truong_gui_xa",
    "khoa_toan_xa",
    "mo_khoa_toan_xa",
    "dieu_hanh_trien_khai_toan_tinh",
    "khoa_toan_tinh",
    "mo_khoa_toan_tinh",
)

ACCESS_FUNCTIONS = (
    "__call__",
    "_co_quyen_theo_thao_tac",
    "_co_quyen_dieu_tra",
    "_kiem_tra_khoa_dot_dieu_tra",
)

LOCK_KEYWORDS = (
    "is_locked",
    "locked_at",
    "locked_by_user_id",
    "lock_reason",
    "status_before_lock",
    "is_province_locked",
    "is_commune_locked",
    "province_locked_at",
    "commune_locked_at",
    "province_lock_reason",
    "commune_lock_reason",
    "school_locked",
    "batch_locked",
    "province_lock_blocks",
    "khoa_truong",
    "mo_khoa_truong",
    "khoa_toan_xa",
    "mo_khoa_toan_xa",
    "khoa_toan_tinh",
    "mo_khoa_toan_tinh",
)

WRITE_DECORATORS = (
    ".post(",
    ".put(",
    ".patch(",
    ".delete(",
)

SAFE_METHOD_MARKERS = (
    "SAFE_METHODS",
    'method in SAFE_METHODS',
)

EXPECTED_CORE_TABLES = (
    "school_years",
    "survey_batches",
    "survey_school_assignments",
    "survey_commune_execution_states",
    "survey_batch_lock_logs",
    "survey_execution_workflow_logs",
)


def section(
    lines: list[str],
    title: str,
) -> None:
    lines.extend(
        [
            "",
            "=" * 132,
            title,
            "=" * 132,
        ]
    )


def sha256_file(
    path: Path,
) -> str:
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


def read_text(
    path: Path,
) -> str:
    return path.read_text(
        encoding="utf-8-sig",
        errors="strict",
    )


def source_segment(
    source: str,
    node: ast.AST,
) -> str:
    value = ast.get_source_segment(
        source,
        node,
    )

    if value:
        return value

    lines = source.splitlines()

    start = max(
        int(
            getattr(
                node,
                "lineno",
                1,
            )
        )
        - 1,
        0,
    )

    end = int(
        getattr(
            node,
            "end_lineno",
            start + 1,
        )
    )

    return "\n".join(
        lines[
            start:end
        ]
    )


def function_nodes(
    source: str,
) -> dict[str, list[ast.AST]]:
    tree = ast.parse(
        source
    )

    result: dict[str, list[ast.AST]] = {}

    for node in ast.walk(
        tree
    ):
        if isinstance(
            node,
            (
                ast.FunctionDef,
                ast.AsyncFunctionDef,
            ),
        ):
            result.setdefault(
                node.name,
                [],
            ).append(
                node
            )

    return result


def decorator_texts(
    source: str,
    node: ast.AST,
) -> list[str]:
    values = []

    for item in getattr(
        node,
        "decorator_list",
        [],
    ):
        text_value = (
            ast.get_source_segment(
                source,
                item,
            )
            or ""
        ).strip()

        if text_value:
            values.append(
                "@"
                + text_value
            )

    return values


def append_function(
    lines: list[str],
    *,
    path: Path,
    source: str,
    funcs: dict[str, list[ast.AST]],
    name: str,
) -> bool:
    nodes = funcs.get(
        name,
        [],
    )

    if not nodes:
        lines.append(
            f"[KHÔNG TÌM THẤY] {path.relative_to(PROJECT)}::{name}"
        )
        return False

    lines.append(
        f"\n### {path.relative_to(PROJECT)}::{name} ###"
    )

    if len(
        nodes
    ) != 1:
        lines.append(
            f"CẢNH BÁO: có {len(nodes)} hàm cùng tên."
        )

    for index, node in enumerate(
        nodes,
        start=1,
    ):
        if len(
            nodes
        ) > 1:
            lines.append(
                f"\n--- instance {index} ---"
            )

        decos = decorator_texts(
            source,
            node,
        )

        if decos:
            lines.append(
                "Decorators: "
                + " | ".join(
                    decos
                )
            )

        lines.append(
            f"Dòng: "
            f"{getattr(node, 'lineno', '?')}"
            f"-{getattr(node, 'end_lineno', '?')}"
        )

        lines.append(
            source_segment(
                source,
                node,
            )
        )

    return True


def find_lock_lines(
    path: Path,
    source: str,
    *,
    max_lines: int = 120,
) -> list[str]:
    result = []

    for number, text_value in enumerate(
        source.splitlines(),
        start=1,
    ):
        lower = text_value.lower()

        if any(
            token.lower()
            in lower
            for token
            in LOCK_KEYWORDS
        ):
            result.append(
                f"{path.relative_to(PROJECT)}:"
                f"{number}: "
                f"{text_value.rstrip()}"
            )

        if len(
            result
        ) >= max_lines:
            result.append(
                "... đã giới hạn số dòng ..."
            )
            break

    return result


def find_route_functions(
    path: Path,
    source: str,
) -> list[dict[str, Any]]:
    tree = ast.parse(
        source
    )

    rows = []

    for node in ast.walk(
        tree
    ):
        if not isinstance(
            node,
            (
                ast.FunctionDef,
                ast.AsyncFunctionDef,
            ),
        ):
            continue

        decorators = decorator_texts(
            source,
            node,
        )

        route_decorators = [
            value
            for value
            in decorators
            if any(
                marker
                in value.lower()
                for marker
                in (
                    ".get(",
                    ".post(",
                    ".put(",
                    ".patch(",
                    ".delete(",
                )
            )
        ]

        if not route_decorators:
            continue

        body = source_segment(
            source,
            node,
        )

        is_write = any(
            marker
            in value.lower()
            for value
            in route_decorators
            for marker
            in WRITE_DECORATORS
        )

        lock_hits = [
            token
            for token
            in LOCK_KEYWORDS
            if token
            in body
        ]

        rows.append(
            {
                "file": str(
                    path.relative_to(
                        PROJECT
                    )
                ),
                "name": node.name,
                "line": int(
                    getattr(
                        node,
                        "lineno",
                        0,
                    )
                ),
                "decorators": route_decorators,
                "is_write": is_write,
                "lock_hits": lock_hits,
            }
        )

    return sorted(
        rows,
        key=lambda item: (
            item["file"],
            item["line"],
        ),
    )


def table_exists(
    con: sqlite3.Connection,
    table: str,
) -> bool:
    value = con.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type='table'
          AND name=?
        LIMIT 1
        """,
        (
            table,
        ),
    ).fetchone()

    return value is not None


def get_tables(
    con: sqlite3.Connection,
) -> list[str]:
    return [
        str(
            row[0]
        )
        for row
        in con.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type='table'
              AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        ).fetchall()
    ]


def table_columns(
    con: sqlite3.Connection,
    table: str,
) -> list[str]:
    return [
        str(
            row[1]
        )
        for row
        in con.execute(
            f'PRAGMA table_info("{table}")'
        ).fetchall()
    ]


def quote_ident(
    value: str,
) -> str:
    return (
        '"'
        + str(
            value
        ).replace(
            '"',
            '""',
        )
        + '"'
    )


def row_count(
    con: sqlite3.Connection,
    table: str,
) -> int:
    value = con.execute(
        f"SELECT COUNT(*) "
        f"FROM {quote_ident(table)}"
    ).fetchone()[0]

    return int(
        value
        or 0
    )


def value_counts(
    con: sqlite3.Connection,
    table: str,
    column: str,
    *,
    limit: int = 30,
) -> list[tuple[Any, int]]:
    rows = con.execute(
        f"""
        SELECT
            {quote_ident(column)} AS value,
            COUNT(*) AS total
        FROM {quote_ident(table)}
        GROUP BY {quote_ident(column)}
        ORDER BY total DESC, value
        LIMIT {int(limit)}
        """
    ).fetchall()

    return [
        (
            row[0],
            int(
                row[1]
                or 0
            ),
        )
        for row
        in rows
    ]


def selected_rows(
    con: sqlite3.Connection,
    table: str,
    columns: list[str],
    *,
    limit: int = 20,
    order_column: str | None = None,
) -> list[sqlite3.Row]:
    if not columns:
        return []

    select_sql = ", ".join(
        quote_ident(
            column
        )
        for column
        in columns
    )

    order_sql = ""

    if (
        order_column
        and order_column
        in table_columns(
            con,
            table,
        )
    ):
        order_sql = (
            " ORDER BY "
            + quote_ident(
                order_column
            )
            + " DESC"
        )

    return con.execute(
        f"""
        SELECT {select_sql}
        FROM {quote_ident(table)}
        {order_sql}
        LIMIT {int(limit)}
        """
    ).fetchall()


def row_text(
    row: sqlite3.Row,
) -> str:
    return " | ".join(
        f"{key}={row[key]!r}"
        for key
        in row.keys()
    )


def lock_relevant_tables(
    con: sqlite3.Connection,
) -> list[tuple[str, list[str]]]:
    results = []

    for table in get_tables(
        con
    ):
        columns = table_columns(
            con,
            table,
        )

        searchable = (
            table.lower()
            + " "
            + " ".join(
                column.lower()
                for column
                in columns
            )
        )

        score_tokens = (
            "lock",
            "locked",
            "survey_batch",
            "survey_school_assignment",
            "execution_state",
            "workflow_log",
        )

        if any(
            token
            in searchable
            for token
            in score_tokens
        ):
            results.append(
                (
                    table,
                    columns,
                )
            )

    return results


def summarize_source(
    report_lines: list[str],
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "workflow_functions": {},
        "access_functions": {},
        "middleware_calls_lock_check": False,
        "access_checks_batch_lock": False,
        "access_checks_school_assignment_lock": False,
        "access_checks_area_lock": False,
        "workflow_has_school_lock": False,
        "workflow_has_commune_lock": False,
        "workflow_has_province_lock": False,
        "workflow_syncs_batch": False,
        "template_lock_ui": False,
    }

    section(
        report_lines,
        "I. SOURCE CHÍNH - SHA256 / AST",
    )

    source_map: dict[Path, str] = {}

    for path in (
        *SOURCE_TARGETS,
        *OPTIONAL_SOURCE_TARGETS,
    ):
        if not path.exists():
            report_lines.append(
                f"[KHÔNG CÓ] "
                f"{path.relative_to(PROJECT)}"
            )
            continue

        source = read_text(
            path
        )

        ast.parse(
            source
        )

        source_map[
            path
        ] = source

        report_lines.append(
            f"[OK] "
            f"{path.relative_to(PROJECT)} "
            f"| lines={len(source.splitlines())} "
            f"| sha256={sha256_file(path)}"
        )

    access_path = (
        APP
        / "access_control.py"
    )

    workflow_path = (
        APP
        / "routers"
        / "survey_school_workflow.py"
    )

    surveys_path = (
        APP
        / "routers"
        / "surveys.py"
    )

    if access_path in source_map:
        access_source = (
            source_map[
                access_path
            ]
        )

        access_funcs = function_nodes(
            access_source
        )

        section(
            report_lines,
            "II. ACCESS CONTROL - CƠ CHẾ CHẶN GHI KHI KHÓA",
        )

        for name in ACCESS_FUNCTIONS:
            found = append_function(
                report_lines,
                path=access_path,
                source=access_source,
                funcs=access_funcs,
                name=name,
            )

            summary[
                "access_functions"
            ][name] = found

        summary[
            "middleware_calls_lock_check"
        ] = (
            "_kiem_tra_khoa_dot_dieu_tra("
            in access_source
        )

        lock_body = ""

        lock_nodes = access_funcs.get(
            "_kiem_tra_khoa_dot_dieu_tra",
            [],
        )

        if lock_nodes:
            lock_body = source_segment(
                access_source,
                lock_nodes[0],
            )

        summary[
            "access_checks_batch_lock"
        ] = (
            "survey_batches"
            in lock_body
            and "is_locked"
            in lock_body
        )

        summary[
            "access_checks_school_assignment_lock"
        ] = (
            (
                "survey_school_assignments"
                in lock_body
                or "SurveySchoolAssignment"
                in lock_body
            )
            and "is_locked"
            in lock_body
        )

        summary[
            "access_checks_area_lock"
        ] = (
            "is_province_locked"
            in lock_body
            or "is_commune_locked"
            in lock_body
        )

        report_lines.extend(
            [
                "",
                "TÓM TẮT ACCESS CONTROL:",
                (
                    " - Middleware gọi "
                    "_kiem_tra_khoa_dot_dieu_tra: "
                    f"{summary['middleware_calls_lock_check']}"
                ),
                (
                    " - Hàm khóa kiểm "
                    "survey_batches.is_locked: "
                    f"{summary['access_checks_batch_lock']}"
                ),
                (
                    " - Hàm khóa kiểm "
                    "survey_school_assignments.is_locked trực tiếp: "
                    f"{summary['access_checks_school_assignment_lock']}"
                ),
                (
                    " - Hàm khóa kiểm "
                    "is_province_locked/is_commune_locked trực tiếp: "
                    f"{summary['access_checks_area_lock']}"
                ),
            ]
        )

    if workflow_path in source_map:
        workflow_source = (
            source_map[
                workflow_path
            ]
        )

        workflow_funcs = function_nodes(
            workflow_source
        )

        section(
            report_lines,
            "III. WORKFLOW TỈNH → XÃ → TRƯỜNG",
        )

        for name in WORKFLOW_FUNCTIONS:
            found = append_function(
                report_lines,
                path=workflow_path,
                source=workflow_source,
                funcs=workflow_funcs,
                name=name,
            )

            summary[
                "workflow_functions"
            ][name] = found

        summary[
            "workflow_has_school_lock"
        ] = all(
            summary[
                "workflow_functions"
            ].get(
                name,
                False,
            )
            for name
            in (
                "khoa_truong",
                "mo_khoa_truong",
            )
        )

        summary[
            "workflow_has_commune_lock"
        ] = all(
            summary[
                "workflow_functions"
            ].get(
                name,
                False,
            )
            for name
            in (
                "khoa_toan_xa",
                "mo_khoa_toan_xa",
            )
        )

        summary[
            "workflow_has_province_lock"
        ] = all(
            summary[
                "workflow_functions"
            ].get(
                name,
                False,
            )
            for name
            in (
                "khoa_toan_tinh",
                "mo_khoa_toan_tinh",
            )
        )

        sync_nodes = workflow_funcs.get(
            "dong_bo_khoa_dot",
            [],
        )

        if sync_nodes:
            sync_body = source_segment(
                workflow_source,
                sync_nodes[0],
            )

            summary[
                "workflow_syncs_batch"
            ] = (
                "batch.is_locked"
                in sync_body
                or "is_locked"
                in sync_body
            )

        report_lines.extend(
            [
                "",
                "TÓM TẮT WORKFLOW:",
                (
                    " - Khóa/mở từng trường: "
                    f"{summary['workflow_has_school_lock']}"
                ),
                (
                    " - Khóa/mở toàn xã: "
                    f"{summary['workflow_has_commune_lock']}"
                ),
                (
                    " - Khóa/mở toàn tỉnh: "
                    f"{summary['workflow_has_province_lock']}"
                ),
                (
                    " - Có helper đồng bộ khóa về batch: "
                    f"{summary['workflow_syncs_batch']}"
                ),
            ]
        )

    if surveys_path in source_map:
        surveys_source = (
            source_map[
                surveys_path
            ]
        )

        section(
            report_lines,
            "IV. SURVEYS.PY - ROUTE GHI VÀ DẤU VẾT KHÓA",
        )

        routes = find_route_functions(
            surveys_path,
            surveys_source,
        )

        write_routes = [
            item
            for item
            in routes
            if item[
                "is_write"
            ]
        ]

        report_lines.append(
            f"Tổng route ghi trong surveys.py: "
            f"{len(write_routes)}"
        )

        for item in write_routes:
            report_lines.append(
                f" - L{item['line']} "
                f"{item['name']} "
                f"| {' ; '.join(item['decorators'])} "
                f"| lock_hits="
                f"{','.join(item['lock_hits']) or '(không trực tiếp)'}"
            )

        report_lines.append(
            "\nCác dòng có từ khóa khóa trong surveys.py:"
        )

        for row in find_lock_lines(
            surveys_path,
            surveys_source,
            max_lines=160,
        ):
            report_lines.append(
                " - "
                + row
            )

    section(
        report_lines,
        "V. QUÉT TOÀN SOURCE APP - DẤU VẾT KHÓA/MỞ",
    )

    scored_files = []

    for path in APP.rglob(
        "*.py"
    ):
        try:
            source = read_text(
                path
            )
        except Exception:
            continue

        lower = source.lower()

        score = sum(
            lower.count(
                token.lower()
            )
            for token
            in LOCK_KEYWORDS
        )

        if score:
            scored_files.append(
                (
                    score,
                    path,
                )
            )

    scored_files.sort(
        key=lambda item: (
            -item[0],
            str(
                item[1]
            ),
        )
    )

    for score, path in scored_files[
        :30
    ]:
        report_lines.append(
            f" - score={score:4d} | "
            f"{path.relative_to(PROJECT)}"
        )

    section(
        report_lines,
        "VI. TEMPLATE / GIAO DIỆN CÓ NÚT KHÓA-MỞ",
    )

    template_hits = []

    templates_root = (
        APP
        / "templates"
    )

    if templates_root.exists():
        tokens = (
            "khoa-toan-tinh",
            "mo-khoa-toan-tinh",
            "khoa-toan-xa",
            "mo-khoa-toan-xa",
            "/khoa",
            "/mo-khoa",
            "Khóa toàn tỉnh",
            "Mở khóa cấp tỉnh",
            "Khóa toàn xã",
            "Mở khóa toàn xã",
            "Khóa trường",
            "Mở khóa trường",
        )

        for path in templates_root.rglob(
            "*.html"
        ):
            try:
                source = read_text(
                    path
                )
            except Exception:
                continue

            for number, text_value in enumerate(
                source.splitlines(),
                start=1,
            ):
                if any(
                    token.lower()
                    in text_value.lower()
                    for token
                    in tokens
                ):
                    template_hits.append(
                        (
                            path,
                            number,
                            text_value.strip(),
                        )
                    )

    summary[
        "template_lock_ui"
    ] = bool(
        template_hits
    )

    report_lines.append(
        f"Tổng dòng giao diện liên quan: "
        f"{len(template_hits)}"
    )

    for path, number, text_value in template_hits[
        :200
    ]:
        report_lines.append(
            f" - "
            f"{path.relative_to(PROJECT)}:"
            f"{number}: "
            f"{text_value}"
        )

    if len(
        template_hits
    ) > 200:
        report_lines.append(
            " ... đã giới hạn 200 dòng ..."
        )

    return summary


def summarize_database(
    report_lines: list[str],
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "tables": [],
        "core_tables": {},
        "area_state_tables": [],
        "batch_has_lock_columns": False,
        "school_assignment_has_lock_columns": False,
        "province_commune_state_exists": False,
        "lock_log_tables": [],
        "locked_batch_count": None,
        "locked_school_assignment_count": None,
        "province_locked_count": None,
        "commune_locked_count": None,
    }

    uri = (
        DB.resolve().as_uri()
        + "?mode=ro"
    )

    con = sqlite3.connect(
        uri,
        uri=True,
    )

    con.row_factory = (
        sqlite3.Row
    )

    try:
        con.execute(
            "PRAGMA query_only = ON"
        )

        integrity = str(
            con.execute(
                "PRAGMA integrity_check"
            ).fetchone()[0]
        )

        fk_rows = con.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()

        section(
            report_lines,
            "VII. DATABASE - HEALTH / SCHEMA KHÓA-MỞ",
        )

        report_lines.extend(
            [
                f"Database: {DB}",
                (
                    "integrity_check: "
                    f"{integrity}"
                ),
                (
                    "foreign_key_check: "
                    f"{len(fk_rows)} lỗi"
                ),
            ]
        )

        tables = get_tables(
            con
        )

        summary[
            "tables"
        ] = tables

        report_lines.append(
            f"Tổng bảng: "
            f"{len(tables)}"
        )

        relevant = (
            lock_relevant_tables(
                con
            )
        )

        report_lines.append(
            "\nBảng/cột liên quan khóa-mở:"
        )

        for table, columns in relevant:
            report_lines.append(
                f" - {table} "
                f"(rows={row_count(con, table)}): "
                + ", ".join(
                    columns
                )
            )

        for table in EXPECTED_CORE_TABLES:
            exists = table_exists(
                con,
                table,
            )

            summary[
                "core_tables"
            ][table] = exists

        section(
            report_lines,
            "VIII. SURVEY_BATCHES - KHÓA CẤP ĐỢT",
        )

        if table_exists(
            con,
            "survey_batches",
        ):
            table = (
                "survey_batches"
            )

            columns = table_columns(
                con,
                table,
            )

            lock_columns = [
                value
                for value
                in (
                    "is_locked",
                    "locked_at",
                    "locked_by_user_id",
                    "lock_reason",
                    "status_before_lock",
                )
                if value
                in columns
            ]

            summary[
                "batch_has_lock_columns"
            ] = (
                "is_locked"
                in columns
            )

            report_lines.append(
                "Columns khóa: "
                + (
                    ", ".join(
                        lock_columns
                    )
                    or "(không có)"
                )
            )

            for column in (
                "status",
                "is_locked",
                "school_year_id",
            ):
                if column in columns:
                    report_lines.append(
                        f"\nPhân bố "
                        f"{column}:"
                    )

                    for value, total in value_counts(
                        con,
                        table,
                        column,
                    ):
                        report_lines.append(
                            f" - "
                            f"{value!r}: "
                            f"{total}"
                        )

            if "is_locked" in columns:
                locked = con.execute(
                    """
                    SELECT COUNT(*)
                    FROM survey_batches
                    WHERE COALESCE(
                        is_locked,
                        0
                    ) = 1
                    """
                ).fetchone()[0]

                summary[
                    "locked_batch_count"
                ] = int(
                    locked
                    or 0
                )

            pick = [
                value
                for value
                in (
                    "id",
                    "code",
                    "school_year_id",
                    "commune_id",
                    "status",
                    "is_locked",
                    "status_before_lock",
                    "locked_at",
                    "locked_by_user_id",
                    "lock_reason",
                    "created_at",
                )
                if value
                in columns
            ]

            report_lines.append(
                "\nTối đa 30 đợt mới nhất:"
            )

            for row in selected_rows(
                con,
                table,
                pick,
                limit=30,
                order_column="id",
            ):
                report_lines.append(
                    " - "
                    + row_text(
                        row
                    )
                )

        else:
            report_lines.append(
                "[KHÔNG CÓ] "
                "survey_batches"
            )

        section(
            report_lines,
            "IX. SURVEY_SCHOOL_ASSIGNMENTS - KHÓA TỪNG TRƯỜNG",
        )

        if table_exists(
            con,
            "survey_school_assignments",
        ):
            table = (
                "survey_school_assignments"
            )

            columns = table_columns(
                con,
                table,
            )

            summary[
                "school_assignment_has_lock_columns"
            ] = (
                "is_locked"
                in columns
            )

            report_lines.append(
                "Columns: "
                + ", ".join(
                    columns
                )
            )

            for column in (
                "status",
                "is_locked",
                "survey_batch_id",
            ):
                if column in columns:
                    report_lines.append(
                        f"\nPhân bố "
                        f"{column}:"
                    )

                    for value, total in value_counts(
                        con,
                        table,
                        column,
                    ):
                        report_lines.append(
                            f" - "
                            f"{value!r}: "
                            f"{total}"
                        )

            if "is_locked" in columns:
                locked = con.execute(
                    """
                    SELECT COUNT(*)
                    FROM survey_school_assignments
                    WHERE COALESCE(
                        is_locked,
                        0
                    ) = 1
                    """
                ).fetchone()[0]

                summary[
                    "locked_school_assignment_count"
                ] = int(
                    locked
                    or 0
                )

            pick = [
                value
                for value
                in (
                    "id",
                    "survey_batch_id",
                    "school_id",
                    "status",
                    "is_locked",
                    "assigned_at",
                    "submitted_at",
                    "reviewed_at",
                    "locked_at",
                    "locked_by_user_id",
                    "lock_reason",
                    "updated_at",
                )
                if value
                in columns
            ]

            report_lines.append(
                "\nTối đa 30 nhiệm vụ trường mới nhất:"
            )

            for row in selected_rows(
                con,
                table,
                pick,
                limit=30,
                order_column="id",
            ):
                report_lines.append(
                    " - "
                    + row_text(
                        row
                    )
                )

        else:
            report_lines.append(
                "[KHÔNG CÓ] "
                "survey_school_assignments"
            )

        section(
            report_lines,
            "X. TRẠNG THÁI KHÓA CẤP TỈNH / XÃ",
        )

        area_tables = []

        for table in tables:
            columns = table_columns(
                con,
                table,
            )

            if (
                "is_province_locked"
                in columns
                or "is_commune_locked"
                in columns
            ):
                area_tables.append(
                    (
                        table,
                        columns,
                    )
                )

        summary[
            "area_state_tables"
        ] = [
            table
            for table, _
            in area_tables
        ]

        summary[
            "province_commune_state_exists"
        ] = bool(
            area_tables
        )

        if not area_tables:
            report_lines.append(
                "[KHÔNG TÌM THẤY] "
                "bảng có is_province_locked/"
                "is_commune_locked."
            )

        for table, columns in area_tables:
            report_lines.append(
                f"\nTABLE: {table} "
                f"| rows={row_count(con, table)}"
            )

            report_lines.append(
                "Columns: "
                + ", ".join(
                    columns
                )
            )

            if (
                "is_province_locked"
                in columns
            ):
                report_lines.append(
                    "Phân bố is_province_locked:"
                )

                values = value_counts(
                    con,
                    table,
                    "is_province_locked",
                )

                for value, total in values:
                    report_lines.append(
                        f" - "
                        f"{value!r}: "
                        f"{total}"
                    )

                locked = con.execute(
                    f"""
                    SELECT COUNT(*)
                    FROM {quote_ident(table)}
                    WHERE COALESCE(
                        is_province_locked,
                        0
                    )=1
                    """
                ).fetchone()[0]

                summary[
                    "province_locked_count"
                ] = (
                    int(
                        locked
                        or 0
                    )
                )

            if (
                "is_commune_locked"
                in columns
            ):
                report_lines.append(
                    "Phân bố is_commune_locked:"
                )

                values = value_counts(
                    con,
                    table,
                    "is_commune_locked",
                )

                for value, total in values:
                    report_lines.append(
                        f" - "
                        f"{value!r}: "
                        f"{total}"
                    )

                locked = con.execute(
                    f"""
                    SELECT COUNT(*)
                    FROM {quote_ident(table)}
                    WHERE COALESCE(
                        is_commune_locked,
                        0
                    )=1
                    """
                ).fetchone()[0]

                summary[
                    "commune_locked_count"
                ] = (
                    int(
                        locked
                        or 0
                    )
                )

            pick = [
                value
                for value
                in (
                    "id",
                    "survey_batch_id",
                    "commune_id",
                    "is_province_locked",
                    "province_locked_at",
                    "province_locked_by_user_id",
                    "province_lock_reason",
                    "is_commune_locked",
                    "commune_locked_at",
                    "commune_locked_by_user_id",
                    "commune_lock_reason",
                    "updated_at",
                )
                if value
                in columns
            ]

            for row in selected_rows(
                con,
                table,
                pick,
                limit=40,
                order_column="id",
            ):
                report_lines.append(
                    " - "
                    + row_text(
                        row
                    )
                )

        section(
            report_lines,
            "XI. NHẬT KÝ KHÓA/MỞ",
        )

        log_tables = []

        for table in tables:
            columns = table_columns(
                con,
                table,
            )

            has_action = (
                "action"
                in columns
            )

            name_match = any(
                token
                in table.lower()
                for token
                in (
                    "lock_log",
                    "workflow_log",
                    "execution_log",
                )
            )

            if (
                has_action
                and name_match
            ):
                log_tables.append(
                    (
                        table,
                        columns,
                    )
                )

        summary[
            "lock_log_tables"
        ] = [
            table
            for table, _
            in log_tables
        ]

        if not log_tables:
            report_lines.append(
                "[KHÔNG TÌM THẤY] "
                "bảng nhật ký khóa/mở."
            )

        for table, columns in log_tables:
            report_lines.append(
                f"\nTABLE: {table} "
                f"| rows={row_count(con, table)}"
            )

            if "action" in columns:
                report_lines.append(
                    "Actions:"
                )

                for value, total in value_counts(
                    con,
                    table,
                    "action",
                    limit=50,
                ):
                    report_lines.append(
                        f" - "
                        f"{value!r}: "
                        f"{total}"
                    )

            pick = [
                value
                for value
                in (
                    "id",
                    "survey_batch_id",
                    "school_id",
                    "commune_id",
                    "action",
                    "actor_user_id",
                    "actor_name_snapshot",
                    "actor_role_snapshot",
                    "reason",
                    "previous_status",
                    "new_status",
                    "form_total",
                    "completed_form_total",
                    "blocking_issue_total",
                    "created_at",
                )
                if value
                in columns
            ]

            report_lines.append(
                "Dòng mới nhất:"
            )

            for row in selected_rows(
                con,
                table,
                pick,
                limit=30,
                order_column=(
                    "id"
                    if "id"
                    in columns
                    else None
                ),
            ):
                report_lines.append(
                    " - "
                    + row_text(
                        row
                    )
                )

        section(
            report_lines,
            "XII. NĂM HỌC / ĐỢT ĐIỀU TRA HIỆN TẠI",
        )

        if table_exists(
            con,
            "school_years",
        ):
            columns = table_columns(
                con,
                "school_years",
            )

            pick = [
                value
                for value
                in (
                    "id",
                    "code",
                    "name",
                    "is_active",
                    "start_date",
                    "end_date",
                    "created_at",
                )
                if value
                in columns
            ]

            for row in selected_rows(
                con,
                "school_years",
                pick,
                limit=50,
                order_column="id",
            ):
                report_lines.append(
                    " - "
                    + row_text(
                        row
                    )
                )

        # Thống kê batch theo năm học bằng schema động.
        if (
            table_exists(
                con,
                "survey_batches",
            )
            and table_exists(
                con,
                "school_years",
            )
        ):
            batch_cols = table_columns(
                con,
                "survey_batches",
            )

            if (
                "school_year_id"
                in batch_cols
            ):
                lock_expr = (
                    "SUM(CASE WHEN "
                    "COALESCE(sb.is_locked,0)=1 "
                    "THEN 1 ELSE 0 END)"
                    if "is_locked"
                    in batch_cols
                    else "0"
                )

                rows = con.execute(
                    f"""
                    SELECT
                        sy.id,
                        sy.code,
                        COUNT(sb.id) AS batch_total,
                        {lock_expr} AS locked_total
                    FROM school_years sy
                    LEFT JOIN survey_batches sb
                      ON sb.school_year_id=sy.id
                    GROUP BY sy.id, sy.code
                    ORDER BY sy.id DESC
                    """
                ).fetchall()

                report_lines.append(
                    "\nĐợt theo năm học:"
                )

                for row in rows:
                    report_lines.append(
                        " - "
                        f"year_id={row[0]} "
                        f"| code={row[1]} "
                        f"| batches={row[2]} "
                        f"| locked={row[3]}"
                    )

        return summary

    finally:
        con.close()


def matrix_line(
    label: str,
    value: bool | None,
    note: str,
) -> str:
    if value is True:
        state = "CÓ"
    elif value is False:
        state = "CHƯA THẤY"
    else:
        state = "CHƯA XÁC ĐỊNH"

    return (
        f" - [{state}] "
        f"{label}: "
        f"{note}"
    )


def main() -> int:
    print(
        "=" * 118
    )
    print(
        "KHẢO SÁT TRẠNG THÁI HIỆN TẠI "
        "CỦA TOÀN BỘ CƠ CHẾ KHÓA / MỞ"
    )
    print(
        "=" * 118
    )
    print()
    print(
        "CHỈ ĐỌC source + database; "
        "không gọi route khóa/mở."
    )
    print(
        "Chỉ tạo 1 file TXT báo cáo trong exports."
    )
    print()

    if not PROJECT.exists():
        print(
            "[LỖI] Không tìm thấy project: "
            + str(
                PROJECT
            )
        )
        return 1

    if not DB.exists():
        print(
            "[LỖI] Không tìm thấy database: "
            + str(
                DB
            )
        )
        return 1

    missing_required = [
        path
        for path
        in SOURCE_TARGETS
        if not path.exists()
    ]

    if missing_required:
        print(
            "[LỖI] Thiếu source bắt buộc:"
        )

        for path in missing_required:
            print(
                " - "
                + str(
                    path
                )
            )

        return 1

    db_hash_before = (
        sha256_file(
            DB
        )
    )

    source_hash_before = {
        str(
            path.relative_to(
                PROJECT
            )
        ): sha256_file(
            path
        )
        for path
        in SOURCE_TARGETS
    }

    report_lines = [
        "=" * 132,
        "KHẢO SÁT TRẠNG THÁI HIỆN TẠI "
        "CỦA TOÀN BỘ CƠ CHẾ KHÓA / MỞ",
        "=" * 132,
        "",
        f"Project: {PROJECT}",
        f"Database: {DB}",
        f"Thời điểm: {datetime.now().isoformat(sep=' ', timespec='seconds')}",
        "",
        "CAM KẾT KHẢO SÁT:",
        " - Không sửa source.",
        " - Không UPDATE/INSERT/DELETE database.",
        " - SQLite mở bằng mode=ro + PRAGMA query_only=ON.",
        " - Không gọi route khóa/mở.",
        " - Chỉ ghi file TXT báo cáo này.",
    ]

    try:
        print(
            "[1/8] SHA256 trước khảo sát: đã chụp."
        )

        source_summary = (
            summarize_source(
                report_lines
            )
        )

        print(
            "[2/8] Source chính: AST OK."
        )

        print(
            "[3/8] Đã khảo sát AccessControl "
            "+ workflow Tỉnh/Xã/Trường."
        )

        print(
            "[4/8] Đã quét route ghi "
            "+ template khóa/mở."
        )

        db_summary = (
            summarize_database(
                report_lines
            )
        )

        print(
            "[5/8] Database: "
            "đã đọc schema/trạng thái khóa."
        )

        section(
            report_lines,
            "XIII. MA TRẬN HIỆN TRẠNG - CHỈ TỪ SOURCE/SCHEMA",
        )

        report_lines.extend(
            [
                matrix_line(
                    "Khóa/mở từng trường",
                    source_summary[
                        "workflow_has_school_lock"
                    ]
                    and db_summary[
                        "school_assignment_has_lock_columns"
                    ],
                    (
                        "Cần có route khoa_truong/mo_khoa_truong "
                        "và survey_school_assignments.is_locked."
                    ),
                ),
                matrix_line(
                    "Khóa/mở toàn xã",
                    source_summary[
                        "workflow_has_commune_lock"
                    ]
                    and db_summary[
                        "province_commune_state_exists"
                    ],
                    (
                        "Cần route khoa_toan_xa/mo_khoa_toan_xa "
                        "và state cấp xã."
                    ),
                ),
                matrix_line(
                    "Khóa/mở toàn tỉnh",
                    source_summary[
                        "workflow_has_province_lock"
                    ]
                    and db_summary[
                        "province_commune_state_exists"
                    ],
                    (
                        "Cần route khoa_toan_tinh/mo_khoa_toan_tinh "
                        "và state cấp tỉnh."
                    ),
                ),
                matrix_line(
                    "Middleware chặn ghi theo khóa đợt",
                    source_summary[
                        "middleware_calls_lock_check"
                    ]
                    and source_summary[
                        "access_checks_batch_lock"
                    ]
                    and db_summary[
                        "batch_has_lock_columns"
                    ],
                    (
                        "Kiểm AccessControlMiddleware "
                        "và survey_batches.is_locked."
                    ),
                ),
                matrix_line(
                    "Khóa xã/tỉnh được đồng bộ về SurveyBatch",
                    source_summary[
                        "workflow_syncs_batch"
                    ],
                    (
                        "Đây là mắt xích để khóa xã/tỉnh "
                        "có thể chặn các POST chung qua middleware."
                    ),
                ),
                matrix_line(
                    "Giao diện có nút khóa/mở",
                    source_summary[
                        "template_lock_ui"
                    ],
                    (
                        "Quét toàn bộ app/templates."
                    ),
                ),
                matrix_line(
                    "Có nhật ký khóa/mở",
                    bool(
                        db_summary[
                            "lock_log_tables"
                        ]
                    ),
                    (
                        "Phát hiện bảng action log liên quan "
                        "lock/workflow."
                    ),
                ),
            ]
        )

        section(
            report_lines,
            "XIV. TRẠNG THÁI KHÓA ĐANG LƯU TRONG DB",
        )

        report_lines.extend(
            [
                (
                    "survey_batches đang khóa: "
                    f"{db_summary['locked_batch_count']!r}"
                ),
                (
                    "survey_school_assignments đang khóa: "
                    f"{db_summary['locked_school_assignment_count']!r}"
                ),
                (
                    "state is_province_locked=1: "
                    f"{db_summary['province_locked_count']!r}"
                ),
                (
                    "state is_commune_locked=1: "
                    f"{db_summary['commune_locked_count']!r}"
                ),
            ]
        )

        section(
            report_lines,
            "XV. ĐIỂM CẦN KIỂM THỬ THỰC TẾ SAU KHẢO SÁT",
        )

        report_lines.extend(
            [
                "1. Chọn một trường có dữ liệu thật.",
                "2. Khóa riêng trường từ tài khoản Xã.",
                "3. Xác nhận Trường/GV bị chặn thao tác ghi nhưng GET/xuất báo cáo còn hoạt động.",
                "4. Mở lại riêng trường và xác nhận quyền ghi phục hồi.",
                "5. Khóa toàn xã và kiểm toàn bộ trường/GV trong xã bị chặn ghi.",
                "6. Mở lại toàn xã.",
                "7. Khóa toàn tỉnh theo năm học và kiểm Xã/Trường/GV bị chặn ghi.",
                "8. Xác nhận Sở vẫn xem/xuất báo cáo được khi khóa.",
                "9. Mở khóa tỉnh và xác nhận trạng thái được phục hồi đúng.",
                "10. Đối chiếu nhật ký khóa/mở sau mỗi thao tác.",
                "",
                "LƯU Ý:",
                " - Mục XV chỉ là kế hoạch kiểm thử tiếp theo.",
                " - Script khảo sát này KHÔNG thực hiện bất kỳ thao tác khóa/mở nào.",
            ]
        )

        db_hash_after = (
            sha256_file(
                DB
            )
        )

        source_hash_after = {
            str(
                path.relative_to(
                    PROJECT
                )
            ): sha256_file(
                path
            )
            for path
            in SOURCE_TARGETS
        }

        section(
            report_lines,
            "XVI. KIỂM TRA AN TOÀN SAU KHẢO SÁT",
        )

        report_lines.extend(
            [
                f"DB SHA256 trước: {db_hash_before}",
                f"DB SHA256 sau  : {db_hash_after}",
                (
                    "Database: "
                    + (
                        "KHÔNG THAY ĐỔI"
                        if db_hash_before
                        == db_hash_after
                        else "ĐÃ THAY ĐỔI - BẤT THƯỜNG"
                    )
                ),
                "",
                "Source SHA256 trước/sau:",
            ]
        )

        source_unchanged = True

        for rel in sorted(
            source_hash_before
        ):
            before = (
                source_hash_before[
                    rel
                ]
            )
            after = (
                source_hash_after[
                    rel
                ]
            )

            same = (
                before
                == after
            )

            if not same:
                source_unchanged = False

            report_lines.append(
                f" - {rel}: "
                + (
                    "KHÔNG THAY ĐỔI"
                    if same
                    else "ĐÃ THAY ĐỔI"
                )
                + f" | {before} -> {after}"
            )

        report_lines.extend(
            [
                "",
                (
                    "Source tổng thể: "
                    + (
                        "KHÔNG THAY ĐỔI"
                        if source_unchanged
                        else "CÓ THAY ĐỔI - BẤT THƯỜNG"
                    )
                ),
                "",
                "KẾT LUẬN:",
                (
                    "KHẢO SÁT HOÀN TẤT - "
                    "CHỈ ĐỌC SOURCE + DATABASE."
                ),
                (
                    "CHƯA THỰC HIỆN KIỂM THỬ "
                    "KHÓA/MỞ THỰC TẾ."
                ),
            ]
        )

        if (
            db_hash_before
            != db_hash_after
            or not source_unchanged
        ):
            raise RuntimeError(
                "Phát hiện source/database thay đổi "
                "trong lúc khảo sát."
            )

        EXPORTS.mkdir(
            parents=True,
            exist_ok=True,
        )

        REPORT.write_text(
            "\n".join(
                report_lines
            ),
            encoding="utf-8-sig",
        )

        print(
            "[6/8] Ma trận hiện trạng: đã lập."
        )

        print(
            "[7/8] Source + Database: "
            "KHÔNG THAY ĐỔI."
        )

        print(
            f"[8/8] Báo cáo: {REPORT}"
        )

        print()
        print(
            "=" * 118
        )
        print(
            "KHẢO SÁT HOÀN TẤT."
        )
        print(
            "Chưa khóa/mở gì."
        )
        print(
            "Source: KHÔNG THAY ĐỔI."
        )
        print(
            "Database: KHÔNG THAY ĐỔI."
        )
        print(
            "=" * 118
        )

        return 0

    except Exception as exc:
        report_lines.extend(
            [
                "",
                "=" * 132,
                "LỖI KHẢO SÁT",
                "=" * 132,
                str(
                    exc
                ),
            ]
        )

        try:
            EXPORTS.mkdir(
                parents=True,
                exist_ok=True,
            )

            REPORT.write_text(
                "\n".join(
                    report_lines
                ),
                encoding="utf-8-sig",
            )
        except Exception:
            pass

        print()
        print(
            "[LỖI] "
            + str(
                exc
            )
        )

        print(
            "Báo cáo tạm: "
            + str(
                REPORT
            )
        )

        return 1


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
