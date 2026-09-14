# -*- coding: utf-8 -*-
"""
BÀI 13B-11.15.2.4.9.2.1
KHÓA ĐƯỜNG TẢI DỮ LIỆU TỪNG XÃ CHO TỔNG HỢP CẤP TỈNH

CHỈ ĐỌC:
- Không sửa source.
- Không sửa database.
- Không sửa template.
- Không gọi exporter để ghi file Excel.

MỤC TIÊU:
1. Khóa chính xác biểu thức gán biến `people` trong:
   - export_mn_report
   - export_additional_report
2. Xác định helper loader là hàm nội bộ hay import.
3. In chữ ký / source helper loader.
4. Liệt kê các helper _load* trong 2 builder.
5. Xác nhận scope province hiện là commune_id=None, school_id=None.
6. Kiểm tra database 130 xã/phường, 51 ĐBKK.
7. Xuất báo cáo TXT để làm nền tạo bộ cài duy nhất Bài 4.9.2.
"""

from __future__ import annotations

import ast
import hashlib
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT = Path(
    os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")
).resolve()

APP = PROJECT / "app"
DB = PROJECT / "data" / "phocap.db"
EXPORTS = PROJECT / "exports"

MN = APP / "pcgd_mn_report_builders_v1.py"
XMC = APP / "pcgd_xmc_report_builders_v1.py"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
OUT = (
    EXPORTS
    / (
        "bao_cao_bai_13b_11_15_2_4_9_2_1_"
        f"khoa_duong_tai_du_lieu_tung_xa_{STAMP}.txt"
    )
)

EXPECTED_COMMUNES = 130
EXPECTED_SPECIAL = 51


def read_text(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(f"Không tìm thấy: {path}")
    return path.read_text(
        encoding="utf-8-sig",
        errors="replace",
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


def db_state() -> dict[str, Any]:
    if not DB.exists():
        raise RuntimeError(f"Không tìm thấy: {DB}")

    uri = DB.resolve().as_uri() + "?mode=ro"
    con = sqlite3.connect(uri, uri=True)

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
                "SELECT COUNT(*) FROM communes"
            ).fetchone()[0]
        )
        special = int(
            con.execute(
                """
                SELECT COUNT(*)
                FROM communes
                WHERE COALESCE(
                    is_special_difficulty_area, 0
                ) = 1
                """
            ).fetchone()[0]
        )

        columns = {
            str(row[1])
            for row in con.execute(
                "PRAGMA table_info(communes)"
            ).fetchall()
        }

        return {
            "integrity": integrity,
            "fk": fk,
            "total": total,
            "special": special,
            "columns": columns,
        }

    finally:
        con.close()


def parse(path: Path):
    source = read_text(path)
    return source, ast.parse(source)


def functions(tree: ast.Module) -> dict[str, ast.AST]:
    return {
        node.name: node
        for node in tree.body
        if isinstance(
            node,
            (
                ast.FunctionDef,
                ast.AsyncFunctionDef,
            ),
        )
    }


def source_segment(
    source: str,
    node: ast.AST,
) -> str:
    lines = source.splitlines()
    return "\n".join(
        lines[
            int(node.lineno) - 1:
            int(node.end_lineno)
        ]
    )


def function_signature(
    source: str,
    node: ast.AST,
) -> str:
    text = source_segment(
        source,
        node,
    )
    first_lines = []

    depth = 0
    started = False

    for line in text.splitlines():
        first_lines.append(line)

        for ch in line:
            if ch == "(":
                depth += 1
                started = True
            elif ch == ")":
                depth -= 1

        if started and depth <= 0:
            break

    return "\n".join(first_lines)


def target_name(target: ast.AST) -> str | None:
    if isinstance(target, ast.Name):
        return target.id
    return None


def find_assignments(
    fn: ast.AST,
    variable: str,
) -> list[ast.AST]:
    hits = []

    for node in ast.walk(fn):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if target_name(target) == variable:
                    hits.append(node)

        elif isinstance(node, ast.AnnAssign):
            if target_name(node.target) == variable:
                hits.append(node)

    hits.sort(
        key=lambda n: (
            int(getattr(n, "lineno", 0)),
            int(getattr(n, "col_offset", 0)),
        )
    )
    return hits


def assigned_value(node: ast.AST) -> ast.AST | None:
    if isinstance(node, ast.Assign):
        return node.value
    if isinstance(node, ast.AnnAssign):
        return node.value
    return None


def root_call_name(expr: ast.AST | None) -> str | None:
    if not isinstance(expr, ast.Call):
        return None

    fn = expr.func

    if isinstance(fn, ast.Name):
        return fn.id

    if isinstance(fn, ast.Attribute):
        parts = []
        cur: ast.AST = fn

        while isinstance(cur, ast.Attribute):
            parts.append(cur.attr)
            cur = cur.value

        if isinstance(cur, ast.Name):
            parts.append(cur.id)

        if parts:
            return ".".join(reversed(parts))

    return None


def import_map(tree: ast.Module) -> dict[str, str]:
    result: dict[str, str] = {}

    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            module = str(node.module or "")
            for alias in node.names:
                bound = alias.asname or alias.name
                result[bound] = (
                    f"from {module} import "
                    f"{alias.name}"
                    + (
                        f" as {alias.asname}"
                        if alias.asname
                        else ""
                    )
                )

        elif isinstance(node, ast.Import):
            for alias in node.names:
                bound = (
                    alias.asname
                    or alias.name.split(".", 1)[0]
                )
                result[bound] = (
                    f"import {alias.name}"
                    + (
                        f" as {alias.asname}"
                        if alias.asname
                        else ""
                    )
                )

    return result


def local_loaders(
    source: str,
    tree: ast.Module,
) -> list[str]:
    funcs = functions(tree)
    rows = []

    for name in sorted(funcs):
        if name.startswith("_load"):
            rows.append(
                function_signature(
                    source,
                    funcs[name],
                )
            )

    return rows


def inspect_export(
    label: str,
    source: str,
    tree: ast.Module,
    fn_name: str,
) -> list[str]:
    funcs = functions(tree)
    imports = import_map(tree)

    if fn_name not in funcs:
        return [
            f"[{label}] Không tìm thấy {fn_name}."
        ]

    fn = funcs[fn_name]
    lines = [
        f"[{label}] {fn_name}",
        "-" * 100,
        "Chữ ký:",
        function_signature(
            source,
            fn,
        ),
        "",
    ]

    people_assigns = find_assignments(
        fn,
        "people",
    )

    lines.append(
        f"Số assignment `people`: "
        f"{len(people_assigns)}"
    )

    for idx, node in enumerate(
        people_assigns,
        start=1,
    ):
        expr = assigned_value(node)
        expression = (
            ast.unparse(expr)
            if expr is not None
            else "(None)"
        )
        call_name = root_call_name(expr)

        lines.extend(
            [
                "",
                f"Assignment people #{idx}:",
                f"  line={node.lineno}",
                f"  expression={expression}",
                f"  root_call={call_name}",
            ]
        )

        if call_name:
            root = call_name.split(".", 1)[0]

            if call_name in funcs:
                helper_node = funcs[call_name]
                lines.append(
                    "  loader_type=LOCAL_FUNCTION"
                )
                lines.append(
                    "  loader_signature:"
                )
                for row in function_signature(
                    source,
                    helper_node,
                ).splitlines():
                    lines.append(
                        "    " + row
                    )

                lines.append(
                    "  loader_source:"
                )
                for row in source_segment(
                    source,
                    helper_node,
                ).splitlines():
                    lines.append(
                        "    " + row
                    )

            elif root in imports:
                lines.append(
                    "  loader_type=IMPORTED_SYMBOL"
                )
                lines.append(
                    "  import="
                    + imports[root]
                )

            else:
                lines.append(
                    "  loader_type="
                    "KHÔNG_XÁC_ĐỊNH_TRỰC_TIẾP"
                )

    lines.extend(
        [
            "",
            "Dấu vết scope trong exporter:",
        ]
    )

    fn_text = source_segment(
        source,
        fn,
    )

    for no, row in enumerate(
        fn_text.splitlines(),
        start=int(fn.lineno),
    ):
        if any(
            token in row
            for token in (
                "selected_commune_id",
                "selected_school_id",
                'meta["kind"]',
                "meta.get",
                "_scope_meta",
                "_effective_scope_for_user",
                "workbook.save",
                "_b491_",
            )
        ):
            lines.append(
                f"  L{no}: {row.rstrip()}"
            )

    return lines


def relevant_imports(
    source: str,
    tree: ast.Module,
) -> list[str]:
    lines = []

    for node in tree.body:
        if isinstance(
            node,
            (
                ast.Import,
                ast.ImportFrom,
            ),
        ):
            text = source_segment(
                source,
                node,
            )

            if any(
                token in text
                for token in (
                    "report",
                    "survey",
                    "pcgd",
                    "models",
                    "loader",
                    "people",
                )
            ):
                lines.append(text)

    return lines


def main() -> int:
    print("=" * 104)
    print(
        "BÀI 13B-11.15.2.4.9.2.1 - "
        "KHÓA ĐƯỜNG TẢI DỮ LIỆU TỪNG XÃ"
    )
    print("=" * 104)
    print()
    print(
        "CHỈ ĐỌC - KHÔNG SỬA SOURCE / DB / TEMPLATE."
    )
    print()

    before_mn = sha256(MN)
    before_xmc = sha256(XMC)

    db = db_state()

    if db["integrity"].lower() != "ok":
        raise RuntimeError(
            "integrity_check != ok"
        )

    if db["fk"] != 0:
        raise RuntimeError(
            f"foreign_key_check có {db['fk']} lỗi."
        )

    if db["total"] != EXPECTED_COMMUNES:
        raise RuntimeError(
            f"communes={db['total']}, "
            f"không phải {EXPECTED_COMMUNES}."
        )

    if db["special"] != EXPECTED_SPECIAL:
        raise RuntimeError(
            f"ĐBKK={db['special']}, "
            f"không phải {EXPECTED_SPECIAL}."
        )

    if (
        "is_special_difficulty_area"
        not in db["columns"]
    ):
        raise RuntimeError(
            "communes thiếu "
            "is_special_difficulty_area."
        )

    mn_source, mn_tree = parse(MN)
    xmc_source, xmc_tree = parse(XMC)

    mn_funcs = functions(mn_tree)
    xmc_funcs = functions(xmc_tree)

    lines = [
        "=" * 104,
        "BÀI 13B-11.15.2.4.9.2.1 - "
        "BÁO CÁO KHÓA ĐƯỜNG TẢI DỮ LIỆU TỪNG XÃ",
        "=" * 104,
        "",
        "I. DATABASE",
        f"integrity_check={db['integrity']}",
        f"foreign_key_check={db['fk']}",
        f"communes={db['total']}",
        f"ĐBKK={db['special']}",
        "",
        "II. MẦM NON",
    ]

    lines.extend(
        inspect_export(
            "MN",
            mn_source,
            mn_tree,
            "export_mn_report",
        )
    )

    lines.extend(
        [
            "",
            "Các helper _load* nội bộ MN:",
        ]
    )

    mn_loaders = local_loaders(
        mn_source,
        mn_tree,
    )

    if mn_loaders:
        for item in mn_loaders:
            for row in item.splitlines():
                lines.append(
                    "  " + row
                )
    else:
        lines.append("  (không có)")

    lines.extend(
        [
            "",
            "Import liên quan MN:",
        ]
    )

    for item in relevant_imports(
        mn_source,
        mn_tree,
    ):
        lines.append(
            "  " + item.replace(
                "\n",
                "\n  ",
            )
        )

    lines.extend(
        [
            "",
            "III. TH / XMC / THCS",
        ]
    )

    lines.extend(
        inspect_export(
            "XMC",
            xmc_source,
            xmc_tree,
            "export_additional_report",
        )
    )

    lines.extend(
        [
            "",
            "Các helper _load* nội bộ XMC:",
        ]
    )

    xmc_loaders = local_loaders(
        xmc_source,
        xmc_tree,
    )

    if xmc_loaders:
        for item in xmc_loaders:
            for row in item.splitlines():
                lines.append(
                    "  " + row
                )
    else:
        lines.append("  (không có)")

    lines.extend(
        [
            "",
            "IV. HELPER _load_people_and_records",
        ]
    )

    for label, source, funcs in (
        ("MN", mn_source, mn_funcs),
        ("XMC", xmc_source, xmc_funcs),
    ):
        lines.append("")
        lines.append(f"[{label}]")

        node = funcs.get(
            "_load_people_and_records"
        )

        if node is None:
            lines.append(
                "  Không định nghĩa nội bộ."
            )
        else:
            lines.append(
                "  Chữ ký:"
            )
            for row in function_signature(
                source,
                node,
            ).splitlines():
                lines.append(
                    "    " + row
                )

            lines.append(
                "  Source:"
            )
            for row in source_segment(
                source,
                node,
            ).splitlines():
                lines.append(
                    "    " + row
                )

    lines.extend(
        [
            "",
            "V. DẤU VẾT BÀI 4.9.1",
            (
                "MN marker helper="
                + str(
                    "BAI_13B_11_15_2_4_9_1_"
                    "MN_HELPERS_START"
                    in mn_source
                )
            ),
            (
                "XMC marker helper="
                + str(
                    "BAI_13B_11_15_2_4_9_1_"
                    "XMC_HELPERS_START"
                    in xmc_source
                )
            ),
            (
                "MN guard commune="
                + str(
                    'str(meta.get("kind") or "") '
                    '!= "commune"'
                    in mn_source
                )
            ),
            (
                "XMC guard commune="
                + str(
                    'str(meta.get("kind") or "") '
                    '!= "commune"'
                    in xmc_source
                )
            ),
        ]
    )

    after_mn = sha256(MN)
    after_xmc = sha256(XMC)

    if before_mn != after_mn:
        raise RuntimeError(
            "MN source thay đổi trong lúc khảo sát."
        )

    if before_xmc != after_xmc:
        raise RuntimeError(
            "XMC source thay đổi trong lúc khảo sát."
        )

    lines.extend(
        [
            "",
            "VI. AN TOÀN",
            f"SHA256 MN={after_mn}",
            f"SHA256 XMC={after_xmc}",
            "Source: KHÔNG THAY ĐỔI.",
            "Database: chỉ mở mode=ro.",
            "",
            "VII. KẾT LUẬN KỸ THUẬT",
            (
                " - export_mn_report có assignment people: "
                + str(
                    len(
                        find_assignments(
                            mn_funcs[
                                "export_mn_report"
                            ],
                            "people",
                        )
                    )
                )
            ),
            (
                " - export_additional_report có assignment people: "
                + str(
                    len(
                        find_assignments(
                            xmc_funcs[
                                "export_additional_report"
                            ],
                            "people",
                        )
                    )
                )
            ),
            " - Báo cáo này dùng để khóa helper loader cho bộ cài Bài 4.9.2.",
        ]
    )

    EXPORTS.mkdir(
        parents=True,
        exist_ok=True,
    )

    OUT.write_text(
        "\n".join(lines),
        encoding="utf-8-sig",
    )

    print(
        f"[1/6] Database: {db['total']} xã/phường; "
        f"ĐBKK={db['special']}; integrity=ok."
    )
    print(
        "[2/6] AST 2 builder: OK."
    )

    mn_assign_count = len(
        find_assignments(
            mn_funcs[
                "export_mn_report"
            ],
            "people",
        )
    )
    xmc_assign_count = len(
        find_assignments(
            xmc_funcs[
                "export_additional_report"
            ],
            "people",
        )
    )

    print(
        f"[3/6] MN export: assignment people="
        f"{mn_assign_count}."
    )
    print(
        f"[4/6] TH/XMC/THCS export: assignment people="
        f"{xmc_assign_count}."
    )
    print(
        "[5/6] Source/DB: KHÔNG THAY ĐỔI."
    )
    print(
        f"[6/6] Báo cáo: {OUT}"
    )
    print()
    print("=" * 104)
    print(
        "BÀI 4.9.2.1 KHẢO SÁT HOÀN THÀNH."
    )
    print(
        "Gửi file TXT này cho ChatGPT để tạo "
        "BỘ CÀI DUY NHẤT Bài 4.9.2."
    )
    print("=" * 104)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
