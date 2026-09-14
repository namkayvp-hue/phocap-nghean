from __future__ import annotations

import ast
import os
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
ROUTER = APP / "routers" / "surveys.py"
DB = PROJECT / "data" / "phocap.db"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

BACKUP = (
    PROJECT
    / "exports"
    / f"backup_bai_13b_11_14_3_3_{STAMP}"
)

ROUTER_BACKUP = (
    BACKUP
    / "app"
    / "routers"
    / "surveys.py"
)

DB_BACKUP = (
    BACKUP
    / "data"
    / "phocap.db"
)

ROUTE_NAME = "theo_doi_nam_hoc_doi_tuong"

LOAD_MARKER = (
    "# === "
    "BAI_13B_11_14_3_LOAD_EVENTS_START"
    " ==="
)


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


def sqlite_backup(
    source: Path,
    target: Path,
) -> None:
    target.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    src = sqlite3.connect(
        str(source)
    )
    dst = sqlite3.connect(
        str(target)
    )

    try:
        src.backup(
            dst
        )
        dst.commit()
    finally:
        dst.close()
        src.close()


def sqlite_restore(
    source: Path,
    target: Path,
) -> None:
    src = sqlite3.connect(
        str(source)
    )
    dst = sqlite3.connect(
        str(target)
    )

    try:
        src.backup(
            dst
        )
        dst.commit()
    finally:
        dst.close()
        src.close()


def db_state():
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

        events_count = int(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM survey_person_events
                """
            ).fetchone()[0]
        )

        return (
            integrity,
            fk_count,
            events_count,
        )

    finally:
        conn.close()


def clear_cache() -> None:
    for cache in APP.rglob(
        "__pycache__"
    ):
        if cache.is_dir():
            shutil.rmtree(
                cache,
                ignore_errors=True,
            )


def find_route_node(
    source: str,
) -> ast.FunctionDef | ast.AsyncFunctionDef:
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
        and node.name == ROUTE_NAME
    ]

    if len(matches) != 1:
        raise RuntimeError(
            f"Phải tìm thấy đúng 1 hàm {ROUTE_NAME}; "
            f"hiện có {len(matches)}."
        )

    return matches[0]


def source_offsets(
    source: str,
) -> list[int]:
    lines = source.splitlines(
        keepends=True
    )

    offsets = [0]

    for line in lines:
        offsets.append(
            offsets[-1]
            + len(line)
        )

    return offsets


def node_span(
    source: str,
    node: ast.AST,
) -> tuple[int, int]:
    offsets = source_offsets(
        source
    )

    if (
        not hasattr(node, "lineno")
        or not hasattr(node, "end_lineno")
    ):
        raise RuntimeError(
            "AST node không có vị trí source."
        )

    start = (
        offsets[
            int(node.lineno) - 1
        ]
        + int(node.col_offset)
    )

    end = (
        offsets[
            int(node.end_lineno) - 1
        ]
        + int(node.end_col_offset)
    )

    return start, end


def call_name(
    call: ast.Call,
) -> str:
    func = call.func

    if isinstance(
        func,
        ast.Name,
    ):
        return func.id

    if isinstance(
        func,
        ast.Attribute,
    ):
        return func.attr

    return ""


def key_string(
    node: ast.AST | None,
) -> str | None:
    if isinstance(
        node,
        ast.Constant,
    ) and isinstance(
        node.value,
        str,
    ):
        return node.value

    return None


def find_selected_year_expression(
    source: str,
    route: ast.FunctionDef | ast.AsyncFunctionDef,
) -> str:
    # 1) Ưu tiên chính giá trị đang dùng cho key
    #    "selected_school_year_id" trong context TemplateResponse.
    for node in ast.walk(
        route
    ):
        if not isinstance(
            node,
            ast.Dict,
        ):
            continue

        for key, value in zip(
            node.keys,
            node.values,
        ):
            if (
                key_string(key)
                == "selected_school_year_id"
            ):
                expression = (
                    ast.get_source_segment(
                        source,
                        value,
                    )
                    or ast.unparse(
                        value
                    )
                ).strip()

                if expression:
                    return expression

    # 2) Nếu context là một biến dict, tìm assignment/update
    #    kiểu context["selected_school_year_id"] = ...
    for node in ast.walk(
        route
    ):
        if not isinstance(
            node,
            (
                ast.Assign,
                ast.AnnAssign,
            ),
        ):
            continue

        targets = (
            node.targets
            if isinstance(
                node,
                ast.Assign,
            )
            else [node.target]
        )

        value = getattr(
            node,
            "value",
            None,
        )

        for target in targets:
            if not isinstance(
                target,
                ast.Subscript,
            ):
                continue

            slice_node = target.slice

            if (
                isinstance(
                    slice_node,
                    ast.Constant,
                )
                and slice_node.value
                == "selected_school_year_id"
            ):
                expression = (
                    ast.get_source_segment(
                        source,
                        value,
                    )
                    or ast.unparse(
                        value
                    )
                ).strip()

                if expression:
                    return expression

    # 3) Fallback an toàn: route thực tế thường nhận
    #    query parameter school_year_id.
    arg_names = {
        arg.arg
        for arg in (
            list(
                route.args.posonlyargs
            )
            + list(
                route.args.args
            )
            + list(
                route.args.kwonlyargs
            )
        )
    }

    if "school_year_id" in arg_names:
        return "school_year_id"

    # 4) Có thể school_year_id được gán cục bộ.
    assigned_names = set()

    for node in ast.walk(
        route
    ):
        if isinstance(
            node,
            ast.Name,
        ) and isinstance(
            node.ctx,
            ast.Store,
        ):
            assigned_names.add(
                node.id
            )

    if "school_year_id" in assigned_names:
        return "school_year_id"

    raise RuntimeError(
        "Không xác định được biểu thức năm học "
        "an toàn cho helper biến động."
    )


def find_event_load_call(
    route: ast.FunctionDef | ast.AsyncFunctionDef,
) -> ast.Call:
    matches = []

    for node in ast.walk(
        route
    ):
        if not isinstance(
            node,
            ast.Call,
        ):
            continue

        if (
            call_name(node)
            == "b131143_load_person_events"
        ):
            matches.append(
                node
            )

    if len(matches) != 1:
        raise RuntimeError(
            "Phải có đúng 1 lời gọi "
            "b131143_load_person_events "
            f"trong route GET; hiện có {len(matches)}."
        )

    call = matches[0]

    if len(call.args) < 3:
        raise RuntimeError(
            "Lời gọi b131143_load_person_events "
            "không đủ 3 tham số."
        )

    return call


def patch_router(
    source: str,
) -> tuple[str, str, str]:
    if LOAD_MARKER not in source:
        raise RuntimeError(
            "Source chưa có block Bài 14.3.2 "
            "để sửa runtime."
        )

    route = find_route_node(
        source
    )

    correct_expression = (
        find_selected_year_expression(
            source,
            route,
        )
    )

    call = find_event_load_call(
        route
    )

    old_arg_node = call.args[2]

    old_expression = (
        ast.get_source_segment(
            source,
            old_arg_node,
        )
        or ast.unparse(
            old_arg_node
        )
    ).strip()

    print(
        "Biểu thức năm học hiện tại:",
        old_expression,
    )

    print(
        "Biểu thức năm học đúng:",
        correct_expression,
    )

    if (
        old_expression
        == correct_expression
    ):
        if (
            old_expression
            == "selected_school_year_id"
        ):
            raise RuntimeError(
                "Biểu thức vẫn là biến undefined "
                "selected_school_year_id."
            )

        print(
            "Lời gọi helper đã dùng đúng biểu thức; "
            "không cần thay."
        )

        return (
            source,
            old_expression,
            correct_expression,
        )

    start, end = node_span(
        source,
        old_arg_node,
    )

    patched = (
        source[:start]
        + correct_expression
        + source[end:]
    )

    ast.parse(
        patched
    )

    # Parse lại và xác nhận lời gọi đã đổi.
    new_route = find_route_node(
        patched
    )

    new_call = find_event_load_call(
        new_route
    )

    new_arg = (
        ast.get_source_segment(
            patched,
            new_call.args[2],
        )
        or ast.unparse(
            new_call.args[2]
        )
    ).strip()

    if (
        new_arg
        != correct_expression
    ):
        raise RuntimeError(
            "Sau patch, tham số năm học "
            "của helper chưa đúng."
        )

    return (
        patched,
        old_expression,
        correct_expression,
    )


def compile_router() -> None:
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
            "py_compile surveys.py không đạt."
        )


def verify_router(
    correct_expression: str,
) -> None:
    source = read_text(
        ROUTER
    )

    route = find_route_node(
        source
    )

    call = find_event_load_call(
        route
    )

    actual_expression = (
        ast.get_source_segment(
            source,
            call.args[2],
        )
        or ast.unparse(
            call.args[2]
        )
    ).strip()

    if (
        actual_expression
        != correct_expression
    ):
        raise RuntimeError(
            "Verify thất bại: helper đang dùng "
            f"{actual_expression!r}, "
            f"mong đợi {correct_expression!r}."
        )

    if (
        actual_expression
        == "selected_school_year_id"
    ):
        raise RuntimeError(
            "Verify thất bại: vẫn còn biến "
            "selected_school_year_id undefined."
        )

    # Nếu expression là Name, phải chắc chắn nó tồn tại
    # dưới dạng tham số hoặc local assignment.
    parsed_expr = ast.parse(
        actual_expression,
        mode="eval",
    ).body

    if isinstance(
        parsed_expr,
        ast.Name,
    ):
        name = parsed_expr.id

        arg_names = {
            arg.arg
            for arg in (
                list(
                    route.args.posonlyargs
                )
                + list(
                    route.args.args
                )
                + list(
                    route.args.kwonlyargs
                )
            )
        }

        stored_names = {
            node.id
            for node in ast.walk(
                route
            )
            if isinstance(
                node,
                ast.Name,
            )
            and isinstance(
                node.ctx,
                ast.Store,
            )
        }

        if (
            name not in arg_names
            and name not in stored_names
        ):
            raise RuntimeError(
                "Biểu thức năm học sau sửa "
                f"vẫn tham chiếu biến chưa định nghĩa: {name}"
            )

    compile_router()


def main() -> int:
    print(
        "=" * 124
    )
    print(
        "BÀI 13B-11.14.3.3 - "
        "SỬA LỖI 500 CƯ TRÚ/BIẾN ĐỘNG: "
        "NameError selected_school_year_id"
    )
    print(
        "=" * 124
    )
    print()
    print(
        "LỖI ĐÃ XÁC ĐỊNH:"
    )
    print(
        " - Route GET theo_doi_nam_hoc_doi_tuong "
        "gọi b131143_load_person_events bằng "
        "selected_school_year_id."
    )
    print(
        " - selected_school_year_id không tồn tại "
        "ở runtime nên trang Năm học trả 500."
    )
    print()
    print(
        "CÁCH SỬA V14.3.3:"
    )
    print(
        " - Đọc AST route GET thật."
    )
    print(
        " - Lấy đúng biểu thức đang truyền cho "
        'context key "selected_school_year_id".'
    )
    print(
        " - Nếu không tìm thấy, mới fallback "
        "sang tham số/local school_year_id."
    )
    print(
        " - Chỉ thay tham số thứ 3 của "
        "b131143_load_person_events."
    )
    print()
    print(
        "AN TOÀN:"
    )
    print(
        " - Chỉ sửa app/routers/surveys.py."
    )
    print(
        " - Không sửa schema/database."
    )
    print(
        " - Không INSERT/UPDATE/DELETE dữ liệu."
    )
    print(
        " - Backup source + database."
    )
    print(
        " - py_compile + integrity + foreign key."
    )
    print(
        " - Có lỗi tự rollback."
    )
    print()

    for path in (
        ROUTER,
        DB,
    ):
        if not path.exists():
            raise RuntimeError(
                f"Không tìm thấy: {path}"
            )

    (
        integrity_before,
        fk_before,
        events_before,
    ) = db_state()

    print(
        "integrity_check trước cài:",
        integrity_before,
    )

    print(
        "foreign_key_check trước cài:",
        fk_before,
        "lỗi",
    )

    print(
        "survey_person_events trước cài:",
        events_before,
        "bản ghi",
    )

    if (
        integrity_before.lower()
        != "ok"
        or fk_before != 0
    ):
        raise RuntimeError(
            "Database không đạt kiểm tra "
            "trước khi cài."
        )

    BACKUP.mkdir(
        parents=True,
        exist_ok=False,
    )

    ROUTER_BACKUP.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    shutil.copy2(
        ROUTER,
        ROUTER_BACKUP,
    )

    sqlite_backup(
        DB,
        DB_BACKUP,
    )

    print(
        "Backup:",
        BACKUP,
    )

    try:
        original = read_text(
            ROUTER
        )

        (
            patched,
            old_expression,
            correct_expression,
        ) = patch_router(
            original
        )

        write_text(
            ROUTER,
            patched,
        )

        verify_router(
            correct_expression
        )

        (
            integrity_after,
            fk_after,
            events_after,
        ) = db_state()

        if (
            events_after
            != events_before
        ):
            raise RuntimeError(
                "Bộ cài không được thay đổi "
                "survey_person_events."
            )

        if (
            integrity_after.lower()
            != "ok"
        ):
            raise RuntimeError(
                "integrity_check sau cài không OK."
            )

        if fk_after != 0:
            raise RuntimeError(
                f"foreign_key_check sau cài có "
                f"{fk_after} lỗi."
            )

        clear_cache()

        print()
        print(
            "KIỂM TRA SAU CÀI:"
        )
        print(
            " - Route GET:",
            ROUTE_NAME,
        )
        print(
            " - Tham số helper trước sửa:",
            old_expression,
        )
        print(
            " - Tham số helper sau sửa:",
            correct_expression,
        )
        print(
            " - Không còn dùng "
            "selected_school_year_id undefined: OK"
        )
        print(
            " - py_compile surveys.py: OK"
        )
        print(
            " - Database không thay đổi: OK"
        )
        print(
            " - survey_person_events:",
            events_after,
            "bản ghi - GIỮ NGUYÊN",
        )
        print(
            " - integrity_check: OK"
        )
        print(
            " - foreign_key_check: 0 lỗi"
        )
        print()
        print(
            "=" * 124
        )
        print(
            "CÀI ĐẶT BÀI 13B-11.14.3.3 THÀNH CÔNG"
        )
        print(
            "=" * 124
        )

        return 0

    except Exception:
        traceback.print_exc()

        print()
        print(
            "CÓ LỖI - "
            "ĐANG KHÔI PHỤC SOURCE VÀ DATABASE..."
        )

        try:
            shutil.copy2(
                ROUTER_BACKUP,
                ROUTER,
            )
            print(
                " - Đã khôi phục surveys.py."
            )
        except Exception as exc:
            print(
                " - Lỗi khôi phục surveys.py:",
                exc,
            )

        try:
            sqlite_restore(
                DB_BACKUP,
                DB,
            )
            print(
                " - Đã khôi phục database."
            )
        except Exception as exc:
            print(
                " - Lỗi khôi phục database:",
                exc,
            )

        clear_cache()

        print(
            "Backup:",
            BACKUP,
        )

        return 1


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
