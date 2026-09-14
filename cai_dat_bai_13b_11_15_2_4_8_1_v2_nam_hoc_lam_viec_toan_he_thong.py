from __future__ import annotations

import ast
import os
import py_compile
import re
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path


PROJECT = Path(
    os.environ.get(
        "PHOCAP_PROJECT",
        r"C:\PhoCap",
    )
).resolve()

APP = PROJECT / "app"
EXPORTS = PROJECT / "exports"
DB = PROJECT / "data" / "phocap.db"

MAIN = APP / "main.py"
MODULE = APP / "working_school_year.py"
PARTIAL = (
    APP
    / "templates"
    / "partials"
    / "dropdown_menu_v1.html"
)
INDEX = (
    APP
    / "templates"
    / "index.html"
)

STAMP = datetime.now().strftime(
    "%Y%m%d_%H%M%S"
)

BACKUP = (
    EXPORTS
    / f"backup_bai_13b_11_15_2_4_8_1_v2_{STAMP}"
)

REPORT = (
    EXPORTS
    / f"bao_cao_bai_13b_11_15_2_4_8_1_v2_{STAMP}.txt"
)

IMPORT_MARKER = (
    "# === BAI_13B_11_15_2_4_8_1_"
    "WORKING_YEAR_IMPORT ==="
)

MIDDLEWARE_START = (
    "# === BAI_13B_11_15_2_4_8_1_"
    "WORKING_YEAR_MIDDLEWARE_START ==="
)

MIDDLEWARE_END = (
    "# === BAI_13B_11_15_2_4_8_1_"
    "WORKING_YEAR_MIDDLEWARE_END ==="
)

SELECTOR_START = (
    "<!-- === BAI_13B_11_15_2_4_8_1_"
    "WORKING_YEAR_SELECTOR_START === -->"
)

SELECTOR_END = (
    "<!-- === BAI_13B_11_15_2_4_8_1_"
    "WORKING_YEAR_SELECTOR_END === -->"
)

MODULE_CODE = 'from __future__ import annotations\n\nfrom typing import Any\nfrom urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit\n\nfrom fastapi import Request\nfrom fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse\nfrom sqlalchemy import select\n\nfrom app.database import get_db\nfrom app.models import SchoolYear\n\n\nSESSION_KEY = "working_school_year_id"\n\nOPTIONS_PATH = "/nam-hoc-lam-viec/options"\nSELECT_PATH = "/nam-hoc-lam-viec/chon"\n\n# Những luồng đặc biệt tự quản lý nhiều năm học hoặc năm nguồn/năm đích.\n# Không ép "Năm học làm việc" vào các luồng này.\nEXCLUDED_PATH_PARTS = (\n    "/static",\n    "/dang-nhap",\n    "/nam-hoc-lam-viec/",\n    "khoi-tao-nam-hoc",\n    "doi-chieu-nam-hoc",\n    "du-lieu-lich-su",\n)\n\n\ndef _db_session():\n    generator = get_db()\n    db = next(generator)\n    return generator, db\n\n\ndef _active_years() -> list[SchoolYear]:\n    generator, db = _db_session()\n\n    try:\n        return list(\n            db.scalars(\n                select(SchoolYear)\n                .where(SchoolYear.is_active.is_(True))\n                .order_by(\n                    SchoolYear.code.desc(),\n                    SchoolYear.id.desc(),\n                )\n            ).all()\n        )\n    finally:\n        generator.close()\n\n\ndef _active_year_ids() -> set[int]:\n    return {\n        int(item.id)\n        for item in _active_years()\n    }\n\n\ndef _default_year_id() -> int | None:\n    years = _active_years()\n\n    if not years:\n        return None\n\n    return int(years[0].id)\n\n\ndef _safe_positive_int(value: Any) -> int | None:\n    try:\n        number = int(str(value).strip())\n    except (TypeError, ValueError):\n        return None\n\n    return number if number > 0 else None\n\n\ndef _should_skip(path: str) -> bool:\n    lowered = str(path or "").lower()\n\n    return any(\n        part in lowered\n        for part in EXCLUDED_PATH_PARTS\n    )\n\n\ndef _replace_year_in_url(\n    target: str,\n    school_year_id: int,\n) -> str:\n    target = str(target or "/").strip()\n\n    if (\n        not target.startswith("/")\n        or target.startswith("//")\n    ):\n        target = "/"\n\n    parts = urlsplit(target)\n\n    query_items = [\n        (key, value)\n        for key, value\n        in parse_qsl(\n            parts.query,\n            keep_blank_values=True,\n        )\n        if key != "school_year_id"\n    ]\n\n    query_items.append(\n        (\n            "school_year_id",\n            str(school_year_id),\n        )\n    )\n\n    return urlunsplit(\n        (\n            "",\n            "",\n            parts.path or "/",\n            urlencode(\n                query_items,\n                doseq=True,\n            ),\n            parts.fragment,\n        )\n    )\n\n\ndef _inject_year_query(\n    scope: dict[str, Any],\n    school_year_id: int,\n) -> None:\n    raw = scope.get(\n        "query_string",\n        b"",\n    )\n\n    text = raw.decode(\n        "latin-1",\n        errors="ignore",\n    )\n\n    items = parse_qsl(\n        text,\n        keep_blank_values=True,\n    )\n\n    if any(\n        key == "school_year_id"\n        for key, _value in items\n    ):\n        return\n\n    items.append(\n        (\n            "school_year_id",\n            str(school_year_id),\n        )\n    )\n\n    scope["query_string"] = urlencode(\n        items,\n        doseq=True,\n    ).encode("latin-1")\n\n\nclass WorkingSchoolYearMiddleware:\n    """\n    Năm học làm việc dùng chung cho một phiên đăng nhập.\n\n    Lưu ý thứ tự middleware:\n    WorkingSchoolYearMiddleware phải được add TRƯỚC SessionMiddleware\n    trong mã nguồn main.py để khi Starlette dựng middleware stack,\n    SessionMiddleware nằm ngoài và tạo scope["session"] trước.\n    """\n\n    def __init__(\n        self,\n        app,\n    ) -> None:\n        self.app = app\n\n    async def __call__(\n        self,\n        scope,\n        receive,\n        send,\n    ) -> None:\n        if scope.get("type") != "http":\n            await self.app(\n                scope,\n                receive,\n                send,\n            )\n            return\n\n        path = str(\n            scope.get(\n                "path",\n                "",\n            )\n            or ""\n        )\n\n        session = scope.get(\n            "session"\n        )\n\n        # Nếu SessionMiddleware chưa chạy thì không can thiệp.\n        if not isinstance(\n            session,\n            dict,\n        ):\n            await self.app(\n                scope,\n                receive,\n                send,\n            )\n            return\n\n        request = Request(\n            scope,\n            receive=receive,\n        )\n\n        if path == OPTIONS_PATH:\n            if session.get(\n                "user_id"\n            ) is None:\n                response = JSONResponse(\n                    {\n                        "ok": False,\n                        "authenticated": False,\n                        "selected_id": None,\n                        "years": [],\n                    },\n                    status_code=401,\n                )\n\n                await response(\n                    scope,\n                    receive,\n                    send,\n                )\n                return\n\n            years = _active_years()\n            valid_ids = {\n                int(item.id)\n                for item in years\n            }\n\n            selected = _safe_positive_int(\n                session.get(\n                    SESSION_KEY\n                )\n            )\n\n            if selected not in valid_ids:\n                selected = (\n                    int(years[0].id)\n                    if years\n                    else None\n                )\n\n                if selected is None:\n                    session.pop(\n                        SESSION_KEY,\n                        None,\n                    )\n                else:\n                    session[\n                        SESSION_KEY\n                    ] = selected\n\n            response = JSONResponse(\n                {\n                    "ok": True,\n                    "authenticated": True,\n                    "selected_id": selected,\n                    "years": [\n                        {\n                            "id": int(item.id),\n                            "code": str(\n                                item.code\n                                or ""\n                            ),\n                            "name": str(\n                                getattr(\n                                    item,\n                                    "name",\n                                    "",\n                                )\n                                or ""\n                            ),\n                        }\n                        for item in years\n                    ],\n                }\n            )\n\n            await response(\n                scope,\n                receive,\n                send,\n            )\n            return\n\n        if path == SELECT_PATH:\n            if session.get(\n                "user_id"\n            ) is None:\n                response = RedirectResponse(\n                    "/dang-nhap",\n                    status_code=303,\n                )\n\n                await response(\n                    scope,\n                    receive,\n                    send,\n                )\n                return\n\n            selected = _safe_positive_int(\n                request.query_params.get(\n                    "school_year_id"\n                )\n            )\n\n            if (\n                selected is None\n                or selected not in _active_year_ids()\n            ):\n                response = PlainTextResponse(\n                    "Năm học không hợp lệ hoặc đã khóa.",\n                    status_code=400,\n                )\n\n                await response(\n                    scope,\n                    receive,\n                    send,\n                )\n                return\n\n            session[\n                SESSION_KEY\n            ] = selected\n\n            target = _replace_year_in_url(\n                request.query_params.get(\n                    "next",\n                    "/",\n                ),\n                selected,\n            )\n\n            response = RedirectResponse(\n                target,\n                status_code=303,\n            )\n\n            await response(\n                scope,\n                receive,\n                send,\n            )\n            return\n\n        # Chỉ áp dụng cho tài khoản đã đăng nhập và GET/HEAD.\n        if (\n            session.get(\n                "user_id"\n            ) is None\n            or scope.get(\n                "method"\n            ) not in {\n                "GET",\n                "HEAD",\n            }\n            or _should_skip(\n                path\n            )\n        ):\n            await self.app(\n                scope,\n                receive,\n                send,\n            )\n            return\n\n        explicit_year = _safe_positive_int(\n            request.query_params.get(\n                "school_year_id"\n            )\n        )\n\n        selected = _safe_positive_int(\n            session.get(\n                SESSION_KEY\n            )\n        )\n\n        # Nếu người dùng đổi Năm học ở một màn hình cũ,\n        # đồng bộ lựa chọn đó thành Năm học làm việc chung.\n        if (\n            explicit_year is not None\n            and explicit_year != selected\n        ):\n            if explicit_year in _active_year_ids():\n                selected = explicit_year\n                session[\n                    SESSION_KEY\n                ] = selected\n\n        if selected is None:\n            selected = _default_year_id()\n\n            if selected is not None:\n                session[\n                    SESSION_KEY\n                ] = selected\n\n        # Không có query riêng -> tự đưa Năm học làm việc vào route cũ.\n        if (\n            selected is not None\n            and explicit_year is None\n        ):\n            _inject_year_query(\n                scope,\n                selected,\n            )\n\n        await self.app(\n            scope,\n            receive,\n            send,\n        )\n'
SELECTOR_SCRIPT = '<!-- === BAI_13B_11_15_2_4_8_1_WORKING_YEAR_SELECTOR_START === -->\n<script>\n(function () {\n    "use strict";\n\n    if (window.__pcWorkingSchoolYearInstalled) {\n        return;\n    }\n\n    window.__pcWorkingSchoolYearInstalled = true;\n\n    function findLogoutButton() {\n        const direct = document.querySelector(\n            ".pc-global-nav__logout"\n        );\n\n        if (direct) {\n            return direct;\n        }\n\n        const buttons = Array.from(\n            document.querySelectorAll(\n                "button, input[type=\'submit\']"\n            )\n        );\n\n        return buttons.find(function (button) {\n            const text = String(\n                button.textContent\n                || button.value\n                || ""\n            ).trim().toLowerCase();\n\n            return text.indexOf(\n                "đăng xuất"\n            ) >= 0;\n        }) || null;\n    }\n\n    function createControl() {\n        if (\n            document.getElementById(\n                "pc-working-school-year"\n            )\n        ) {\n            return null;\n        }\n\n        const wrap = document.createElement(\n            "div"\n        );\n\n        wrap.id =\n            "pc-working-school-year";\n\n        wrap.style.display = "flex";\n        wrap.style.alignItems = "center";\n        wrap.style.gap = "6px";\n        wrap.style.margin = "4px 8px";\n        wrap.style.padding = "4px 8px";\n        wrap.style.borderRadius = "8px";\n        wrap.style.background =\n            "rgba(255,255,255,.14)";\n        wrap.style.whiteSpace = "nowrap";\n\n        const label = document.createElement(\n            "label"\n        );\n\n        label.htmlFor =\n            "pc-working-school-year-select";\n        label.textContent = "Năm học:";\n        label.style.fontSize = "12px";\n        label.style.fontWeight = "700";\n        label.style.color = "inherit";\n\n        const select = document.createElement(\n            "select"\n        );\n\n        select.id =\n            "pc-working-school-year-select";\n        select.setAttribute(\n            "aria-label",\n            "Năm học làm việc"\n        );\n        select.style.minWidth = "112px";\n        select.style.height = "30px";\n        select.style.border = "1px solid rgba(255,255,255,.45)";\n        select.style.borderRadius = "6px";\n        select.style.padding = "2px 6px";\n        select.style.background = "#ffffff";\n        select.style.color = "#17324d";\n        select.style.fontWeight = "700";\n        select.style.fontSize = "12px";\n\n        const loading =\n            document.createElement(\n                "option"\n            );\n\n        loading.value = "";\n        loading.textContent = "Đang tải...";\n        select.appendChild(\n            loading\n        );\n\n        wrap.appendChild(\n            label\n        );\n\n        wrap.appendChild(\n            select\n        );\n\n        return {\n            wrap: wrap,\n            select: select,\n        };\n    }\n\n    function currentNextUrl() {\n        return (\n            window.location.pathname\n            + window.location.search\n            + window.location.hash\n        );\n    }\n\n    function installControl() {\n        const logout =\n            findLogoutButton();\n\n        if (!logout) {\n            return;\n        }\n\n        const created =\n            createControl();\n\n        if (!created) {\n            return;\n        }\n\n        const logoutForm =\n            logout.closest(\n                "form"\n            );\n\n        const host = (\n            logoutForm\n            && logoutForm.parentElement\n        )\n            ? logoutForm.parentElement\n            : logout.parentElement;\n\n        if (!host) {\n            return;\n        }\n\n        if (\n            logoutForm\n            && logoutForm.parentElement\n                === host\n        ) {\n            host.insertBefore(\n                created.wrap,\n                logoutForm\n            );\n        } else {\n            host.insertBefore(\n                created.wrap,\n                logout\n            );\n        }\n\n        fetch(\n            "/nam-hoc-lam-viec/options",\n            {\n                credentials: "same-origin",\n                headers: {\n                    "Accept": "application/json"\n                }\n            }\n        )\n        .then(function (response) {\n            if (!response.ok) {\n                throw new Error(\n                    "Không tải được năm học."\n                );\n            }\n\n            return response.json();\n        })\n        .then(function (data) {\n            const select =\n                created.select;\n\n            select.innerHTML = "";\n\n            const years =\n                Array.isArray(\n                    data.years\n                )\n                    ? data.years\n                    : [];\n\n            if (!years.length) {\n                const empty =\n                    document.createElement(\n                        "option"\n                    );\n\n                empty.value = "";\n                empty.textContent =\n                    "Chưa có năm học";\n                select.appendChild(\n                    empty\n                );\n                select.disabled = true;\n                return;\n            }\n\n            years.forEach(\n                function (year) {\n                    const option =\n                        document.createElement(\n                            "option"\n                        );\n\n                    option.value =\n                        String(\n                            year.id\n                        );\n\n                    option.textContent =\n                        String(\n                            year.code\n                            || year.name\n                            || year.id\n                        );\n\n                    if (\n                        Number(\n                            year.id\n                        )\n                        === Number(\n                            data.selected_id\n                        )\n                    ) {\n                        option.selected = true;\n                    }\n\n                    select.appendChild(\n                        option\n                    );\n                }\n            );\n\n            select.addEventListener(\n                "change",\n                function () {\n                    const yearId =\n                        String(\n                            select.value\n                            || ""\n                        );\n\n                    if (!yearId) {\n                        return;\n                    }\n\n                    const target =\n                        "/nam-hoc-lam-viec/chon"\n                        + "?school_year_id="\n                        + encodeURIComponent(\n                            yearId\n                        )\n                        + "&next="\n                        + encodeURIComponent(\n                            currentNextUrl()\n                        );\n\n                    window.location.assign(\n                        target\n                    );\n                }\n            );\n        })\n        .catch(function () {\n            created.select.innerHTML =\n                "<option value=\'\'>Năm học</option>";\n        });\n    }\n\n    if (\n        document.readyState\n        === "loading"\n    ) {\n        document.addEventListener(\n            "DOMContentLoaded",\n            installControl,\n            {\n                once: true\n            }\n        );\n    } else {\n        installControl();\n    }\n})();\n</script>\n<!-- === BAI_13B_11_15_2_4_8_1_WORKING_YEAR_SELECTOR_END === -->'


def read_text(
    path: Path,
) -> str:
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


def db_state() -> dict:
    if not DB.exists():
        raise RuntimeError(
            f"Không tìm thấy database: {DB}"
        )

    conn = sqlite3.connect(
        str(DB)
    )

    try:
        return {
            "integrity": str(
                conn.execute(
                    "PRAGMA integrity_check"
                ).fetchone()[0]
            ),
            "fk_count": len(
                conn.execute(
                    "PRAGMA foreign_key_check"
                ).fetchall()
            ),
            "school_year_count": int(
                conn.execute(
                    "SELECT COUNT(*) "
                    "FROM school_years"
                ).fetchone()[0]
            ),
            "active_year_count": int(
                conn.execute(
                    "SELECT COUNT(*) "
                    "FROM school_years "
                    "WHERE is_active = 1"
                ).fetchone()[0]
            ),
            "user_count": int(
                conn.execute(
                    "SELECT COUNT(*) "
                    "FROM users"
                ).fetchone()[0]
            ),
        }

    finally:
        conn.close()


def backup_database() -> None:
    src = sqlite3.connect(
        str(DB)
    )

    dst = sqlite3.connect(
        str(
            BACKUP
            / DB.name
        )
    )

    try:
        src.backup(
            dst
        )
    finally:
        dst.close()
        src.close()


def _call_name(
    node,
) -> str:
    if isinstance(
        node,
        ast.Name,
    ):
        return node.id

    if isinstance(
        node,
        ast.Attribute,
    ):
        return node.attr

    return ""


def _middleware_first_arg_name(
    node,
) -> str:
    if not isinstance(
        node,
        ast.Call,
    ):
        return ""

    if _call_name(
        node.func
    ) != "Middleware":
        return ""

    if not node.args:
        return ""

    return _call_name(
        node.args[0]
    )


def _add_middleware_first_arg_name(
    node,
) -> str:
    if not isinstance(
        node,
        ast.Call,
    ):
        return ""

    if not isinstance(
        node.func,
        ast.Attribute,
    ):
        return ""

    if (
        node.func.attr
        != "add_middleware"
    ):
        return ""

    if not node.args:
        return ""

    return _call_name(
        node.args[0]
    )


def _find_session_list_call(
    source: str,
):
    tree = ast.parse(
        source
    )

    parents = {}

    for parent in ast.walk(
        tree
    ):
        for child in ast.iter_child_nodes(
            parent
        ):
            parents[id(child)] = parent

    for node in ast.walk(
        tree
    ):
        if (
            isinstance(
                node,
                ast.Call,
            )
            and _middleware_first_arg_name(
                node
            )
            == "SessionMiddleware"
        ):
            parent = parents.get(
                id(node)
            )

            if isinstance(
                parent,
                (
                    ast.List,
                    ast.Tuple,
                ),
            ):
                return (
                    node,
                    parent,
                )

    return (
        None,
        None,
    )


def _patch_middleware_list(
    source: str,
) -> tuple[str, str]:
    session_call, container = (
        _find_session_list_call(
            source
        )
    )

    if (
        session_call is None
        or container is None
    ):
        raise RuntimeError(
            "Không tìm thấy cấu hình "
            "Middleware(SessionMiddleware, ...)."
        )

    lines = source.splitlines(
        keepends=True
    )

    end_index = int(
        session_call.end_lineno
    ) - 1

    if (
        end_index < 0
        or end_index >= len(
            lines
        )
    ):
        raise RuntimeError(
            "Không xác định được dòng kết thúc "
            "SessionMiddleware."
        )

    end_line = lines[
        end_index
    ]

    end_col = int(
        session_call.end_col_offset
    )

    tail = end_line[
        end_col:
    ]

    if "," not in tail:
        newline = ""

        if end_line.endswith(
            "\r\n"
        ):
            newline = "\r\n"
            body = end_line[:-2]
        elif end_line.endswith(
            "\n"
        ):
            newline = "\n"
            body = end_line[:-1]
        else:
            body = end_line

        lines[
            end_index
        ] = (
            body[:end_col]
            + ","
            + body[end_col:]
            + newline
        )

    indent = " " * int(
        session_call.col_offset
    )

    insertion = (
        f"{indent}{MIDDLEWARE_START}\n"
        f"{indent}Middleware("
        "WorkingSchoolYearMiddleware),\n"
        f"{indent}{MIDDLEWARE_END}\n"
    )

    lines.insert(
        end_index + 1,
        insertion,
    )

    patched = "".join(
        lines
    )

    ast.parse(
        patched
    )

    return (
        patched,
        "Đã nối Năm học làm việc vào "
        "danh sách Middleware ngay SAU SessionMiddleware.",
    )


def _patch_add_middleware(
    source: str,
) -> tuple[str, str]:
    tree = ast.parse(
        source
    )

    target = None

    for node in ast.walk(
        tree
    ):
        if (
            isinstance(
                node,
                ast.Call,
            )
            and _add_middleware_first_arg_name(
                node
            )
            == "SessionMiddleware"
        ):
            target = node
            break

    if target is None:
        raise RuntimeError(
            "Không tìm thấy cấu hình "
            "app.add_middleware(SessionMiddleware...)."
        )

    lines = source.splitlines(
        keepends=True
    )

    line_index = int(
        target.lineno
    ) - 1

    if (
        line_index < 0
        or line_index >= len(
            lines
        )
    ):
        raise RuntimeError(
            "Không xác định được dòng "
            "app.add_middleware(SessionMiddleware...)."
        )

    line = lines[
        line_index
    ]

    indent = line[
        :len(line)
        - len(
            line.lstrip(
                " \t"
            )
        )
    ]

    block = (
        f"{indent}{MIDDLEWARE_START}\n"
        f"{indent}app.add_middleware("
        "WorkingSchoolYearMiddleware)\n"
        f"{indent}{MIDDLEWARE_END}\n"
    )

    lines.insert(
        line_index,
        block,
    )

    patched = "".join(
        lines
    )

    ast.parse(
        patched
    )

    return (
        patched,
        "Đã add Năm học làm việc TRƯỚC "
        "SessionMiddleware theo kiểu add_middleware.",
    )


def patch_main(
    source: str,
) -> tuple[str, list[str]]:
    notes: list[str] = []

    ast.parse(
        source
    )

    if (
        "from starlette.middleware.sessions "
        "import SessionMiddleware"
        not in source
    ):
        raise RuntimeError(
            "Không tìm thấy SessionMiddleware "
            "đúng như báo cáo khảo sát."
        )

    if IMPORT_MARKER not in source:
        anchor = (
            "from starlette.middleware.sessions "
            "import SessionMiddleware"
        )

        pos = source.find(
            anchor
        )

        line_end = source.find(
            "\n",
            pos,
        )

        if (
            pos < 0
            or line_end < 0
        ):
            raise RuntimeError(
                "Không xác định được vị trí import "
                "SessionMiddleware."
            )

        insertion = (
            "\n"
            + IMPORT_MARKER
            + "\n"
            + "from app.working_school_year "
              "import WorkingSchoolYearMiddleware\n"
        )

        source = (
            source[:line_end + 1]
            + insertion
            + source[line_end + 1:]
        )

        notes.append(
            "Đã nối WorkingSchoolYearMiddleware "
            "vào main.py."
        )

    if MIDDLEWARE_START not in source:
        session_call, container = (
            _find_session_list_call(
                source
            )
        )

        if (
            session_call is not None
            and container is not None
        ):
            source, note = (
                _patch_middleware_list(
                    source
                )
            )
        else:
            source, note = (
                _patch_add_middleware(
                    source
                )
            )

        notes.append(
            note
        )

    verify_main(
        source
    )

    return (
        source,
        notes,
    )

def patch_partial(
    source: str,
) -> tuple[str, str]:
    if (
        "pc-global-nav__logout"
        not in source
    ):
        raise RuntimeError(
            "dropdown_menu_v1.html "
            "không có nút đăng xuất chuẩn."
        )

    if SELECTOR_START in source:
        return (
            source,
            "Selector ở menu chung đã tồn tại.",
        )

    return (
        source.rstrip()
        + "\n\n"
        + SELECTOR_SCRIPT
        + "\n",
        "Đã thêm selector Năm học làm việc "
        "vào menu chung.",
    )


def patch_index(
    source: str,
) -> tuple[str, str]:
    if (
        "Đăng xuất"
        not in source
    ):
        raise RuntimeError(
            "index.html không có nút Đăng xuất."
        )

    if SELECTOR_START in source:
        return (
            source,
            "Selector ở trang chủ đã tồn tại.",
        )

    pos = source.lower().rfind(
        "</body>"
    )

    if pos < 0:
        raise RuntimeError(
            "index.html không có </body>."
        )

    return (
        source[:pos]
        + "\n"
        + SELECTOR_SCRIPT
        + "\n"
        + source[pos:],
        "Đã thêm selector Năm học làm việc "
        "vào trang chủ.",
    )


def verify_main(
    source: str,
) -> None:
    tree = ast.parse(
        source
    )

    required = (
        IMPORT_MARKER,
        "from app.working_school_year "
        "import WorkingSchoolYearMiddleware",
        MIDDLEWARE_START,
        MIDDLEWARE_END,
        "SessionMiddleware",
    )

    for token in required:
        if token not in source:
            raise RuntimeError(
                "Verifier main thiếu: "
                + token
            )

    parents = {}

    for parent in ast.walk(
        tree
    ):
        for child in ast.iter_child_nodes(
            parent
        ):
            parents[id(child)] = parent

    session_info = None
    working_info = None

    for node in ast.walk(
        tree
    ):
        if not isinstance(
            node,
            ast.Call,
        ):
            continue

        arg_name = (
            _middleware_first_arg_name(
                node
            )
        )

        if arg_name in {
            "SessionMiddleware",
            "WorkingSchoolYearMiddleware",
        }:
            parent = parents.get(
                id(node)
            )

            if isinstance(
                parent,
                (
                    ast.List,
                    ast.Tuple,
                ),
            ):
                try:
                    idx = parent.elts.index(
                        node
                    )
                except ValueError:
                    idx = None

                if idx is not None:
                    if (
                        arg_name
                        == "SessionMiddleware"
                    ):
                        session_info = (
                            parent,
                            idx,
                        )

                    if (
                        arg_name
                        == "WorkingSchoolYearMiddleware"
                    ):
                        working_info = (
                            parent,
                            idx,
                        )

    if (
        session_info is not None
        and working_info is not None
        and session_info[0]
        is working_info[0]
    ):
        if not (
            session_info[1]
            < working_info[1]
        ):
            raise RuntimeError(
                "Trong danh sách middleware, "
                "SessionMiddleware phải đứng trước "
                "WorkingSchoolYearMiddleware "
                "để session bao ngoài."
            )

        return

    session_add = None
    working_add = None

    for node in ast.walk(
        tree
    ):
        if not isinstance(
            node,
            ast.Call,
        ):
            continue

        arg_name = (
            _add_middleware_first_arg_name(
                node
            )
        )

        if (
            arg_name
            == "SessionMiddleware"
        ):
            session_add = node

        if (
            arg_name
            == "WorkingSchoolYearMiddleware"
        ):
            working_add = node

    if (
        session_add is not None
        and working_add is not None
    ):
        if not (
            (
                int(
                    working_add.lineno
                ),
                int(
                    working_add.col_offset
                ),
            )
            <
            (
                int(
                    session_add.lineno
                ),
                int(
                    session_add.col_offset
                ),
            )
        ):
            raise RuntimeError(
                "Theo kiểu add_middleware, "
                "Working phải được add trước "
                "Session trong source."
            )

        return

    raise RuntimeError(
        "Verifier không xác định được "
        "cặp SessionMiddleware / "
        "WorkingSchoolYearMiddleware "
        "sau khi vá."
    )

def verify_module(
    source: str,
) -> None:
    ast.parse(
        source
    )

    required = (
        'SESSION_KEY = "working_school_year_id"',
        'OPTIONS_PATH = "/nam-hoc-lam-viec/options"',
        'SELECT_PATH = "/nam-hoc-lam-viec/chon"',
        "class WorkingSchoolYearMiddleware",
        "_inject_year_query(",
        "session[",
        "SchoolYear.is_active.is_(True)",
        '"khoi-tao-nam-hoc"',
        '"doi-chieu-nam-hoc"',
        '"du-lieu-lich-su"',
    )

    for token in required:
        if token not in source:
            raise RuntimeError(
                "Verifier module thiếu: "
                + token
            )


def verify_template(
    source: str,
    *,
    name: str,
) -> None:
    for token in (
        SELECTOR_START,
        SELECTOR_END,
        "pc-working-school-year-select",
        "/nam-hoc-lam-viec/options",
        "/nam-hoc-lam-viec/chon",
        "Năm học:",
    ):
        if token not in source:
            raise RuntimeError(
                f"Verifier {name} thiếu: "
                + token
            )

    block = source[
        source.find(
            SELECTOR_START
        ):
        source.find(
            SELECTOR_END
        )
        + len(
            SELECTOR_END
        )
    ]

    if (
        "MutationObserver"
        in block
    ):
        raise RuntimeError(
            f"{name}: không cho phép MutationObserver."
        )

    from jinja2 import Environment

    Environment().parse(
        source
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


def main() -> None:
    print("=" * 148)
    print(
        "BÀI 13B-11.15.2.4.8.1 V2 - "
        "NĂM HỌC LÀM VIỆC TOÀN HỆ THỐNG"
    )
    print("=" * 148)
    print()

    print("SẼ LÀM:")
    print(
        " - Sau đăng nhập có ô 'Năm học' "
        "trên thanh tài khoản."
    )
    print(
        " - Chọn một lần, lưu trong session "
        "working_school_year_id."
    )
    print(
        " - GET route cũ không truyền school_year_id "
        "sẽ tự nhận Năm học làm việc."
    )
    print(
        " - Nếu đổi năm học ở màn hình cũ, "
        "session được đồng bộ theo."
    )
    print(
        " - Áp dụng Sở / Xã / Trường / Giáo viên."
    )
    print()

    print("GIỮ NGUYÊN:")
    print(
        " - Không đổi database/schema/dữ liệu."
    )
    print(
        " - Không xóa dropdown Năm học cũ."
    )
    print(
        " - Không đổi route nghiệp vụ hiện có."
    )
    print(
        " - Không đổi quyền khóa/mở dữ liệu."
    )
    print(
        " - Luồng khởi tạo năm học / đối chiếu liên năm / "
        "dữ liệu lịch sử không bị ép năm học."
    )
    print(
        " - Không MutationObserver."
    )
    print()

    for path in (
        MAIN,
        PARTIAL,
        INDEX,
        DB,
    ):
        if not path.exists():
            raise RuntimeError(
                f"Không tìm thấy: {path}"
            )

    old_main = read_text(
        MAIN
    )

    old_partial = read_text(
        PARTIAL
    )

    old_index = read_text(
        INDEX
    )

    old_module = (
        read_text(
            MODULE
        )
        if MODULE.exists()
        else None
    )

    ast.parse(
        old_main
    )

    new_main, main_notes = patch_main(
        old_main
    )

    new_partial, partial_note = patch_partial(
        old_partial
    )

    new_index, index_note = patch_index(
        old_index
    )

    verify_main(
        new_main
    )

    verify_module(
        MODULE_CODE
    )

    verify_template(
        new_partial,
        name="dropdown_menu_v1.html",
    )

    verify_template(
        new_index,
        name="index.html",
    )

    before_db = db_state()

    if (
        before_db["integrity"]
        != "ok"
    ):
        raise RuntimeError(
            "Database integrity_check != ok trước cài."
        )

    if (
        before_db["fk_count"]
        != 0
    ):
        raise RuntimeError(
            "Database có lỗi foreign key trước cài."
        )

    if (
        before_db["active_year_count"]
        <= 0
    ):
        raise RuntimeError(
            "Không có năm học đang hoạt động; "
            "chưa thể bật Năm học làm việc."
        )

    EXPORTS.mkdir(
        parents=True,
        exist_ok=True,
    )

    BACKUP.mkdir(
        parents=True,
        exist_ok=False,
    )

    for path in (
        MAIN,
        PARTIAL,
        INDEX,
    ):
        shutil.copy2(
            path,
            BACKUP / path.name,
        )

    if MODULE.exists():
        shutil.copy2(
            MODULE,
            BACKUP
            / (
                MODULE.name
                + ".before"
            ),
        )

    backup_database()

    try:
        write_text(
            MODULE,
            MODULE_CODE,
        )

        if (
            new_main
            != old_main
        ):
            write_text(
                MAIN,
                new_main,
            )

        if (
            new_partial
            != old_partial
        ):
            write_text(
                PARTIAL,
                new_partial,
            )

        if (
            new_index
            != old_index
        ):
            write_text(
                INDEX,
                new_index,
            )

        py_compile.compile(
            str(MODULE),
            doraise=True,
        )

        py_compile.compile(
            str(MAIN),
            doraise=True,
        )

        verify_module(
            read_text(
                MODULE
            )
        )

        verify_main(
            read_text(
                MAIN
            )
        )

        verify_template(
            read_text(
                PARTIAL
            ),
            name="dropdown_menu_v1.html",
        )

        verify_template(
            read_text(
                INDEX
            ),
            name="index.html",
        )

        after_db = db_state()

        if (
            after_db
            != before_db
        ):
            raise RuntimeError(
                "Database thay đổi ngoài dự kiến."
            )

        clear_cache()

    except Exception:
        print()
        print(
            "CÓ LỖI - ĐANG ROLLBACK..."
        )

        shutil.copy2(
            BACKUP / MAIN.name,
            MAIN,
        )

        shutil.copy2(
            BACKUP / PARTIAL.name,
            PARTIAL,
        )

        shutil.copy2(
            BACKUP / INDEX.name,
            INDEX,
        )

        if (
            old_module
            is None
        ):
            if MODULE.exists():
                MODULE.unlink()
        else:
            write_text(
                MODULE,
                old_module,
            )

        clear_cache()
        raise

    notes = (
        main_notes
        + [
            partial_note,
            index_note,
        ]
    )

    lines = [
        "=" * 148,
        "BÀI 13B-11.15.2.4.8.1 V2 - KẾT QUẢ",
        "=" * 148,
        "",
        "ĐÃ CÀI:",
        " - app/working_school_year.py",
        " - WorkingSchoolYearMiddleware nối vào main.py.",
        " - Selector Năm học làm việc ở menu chung.",
        " - Selector Năm học làm việc ở trang chủ.",
        "",
        "CƠ CHẾ:",
        " - Session key: working_school_year_id.",
        " - Năm mặc định: năm active mới nhất.",
        " - Route cũ thiếu school_year_id: middleware tự đưa năm session vào.",
        " - Route cũ có school_year_id hợp lệ: đồng bộ lại session.",
        " - Đăng xuất request.session.clear() sẽ xóa năm làm việc theo cơ chế cũ.",
        "",
        "LOẠI TRỪ AN TOÀN:",
        " - Khởi tạo năm học.",
        " - Đối chiếu giữa các năm học.",
        " - Dữ liệu lịch sử.",
        "",
        "DB TRƯỚC/SAU:",
        repr(before_db),
        "",
        "GHI CHÚ:",
    ]

    for note in notes:
        lines.append(
            " - "
            + note
        )

    lines.extend(
        [
            "",
            "AN TOÀN:",
            " - Không ALTER TABLE.",
            " - Không UPDATE/INSERT/DELETE database.",
            " - Không xóa dropdown cũ.",
            " - Không MutationObserver.",
            f" - Backup: {BACKUP}",
            "",
        ]
    )

    REPORT.write_text(
        "\n".join(
            lines
        ),
        encoding="utf-8",
    )

    print("KIỂM TRA:")
    print(
        " - SessionMiddleware nền: OK"
    )
    print(
        " - Working middleware thứ tự: OK"
    )
    print(
        " - py_compile main/module: OK"
    )
    print(
        " - Jinja parse 2 template: OK"
    )
    print(
        " - Năm active:",
        before_db[
            "active_year_count"
        ],
    )
    print(
        " - integrity_check: OK"
    )
    print(
        " - foreign_key_check: 0"
    )
    print(
        " - Database không thay đổi: OK"
    )
    print(
        " - Không MutationObserver: OK"
    )
    print()
    print(
        "Backup:",
        BACKUP,
    )
    print(
        "Báo cáo:",
        REPORT,
    )
    print()
    print("=" * 148)
    print(
        "BÀI 13B-11.15.2.4.8.1 V2 THÀNH CÔNG"
    )
    print("=" * 148)


if __name__ == "__main__":
    main()
