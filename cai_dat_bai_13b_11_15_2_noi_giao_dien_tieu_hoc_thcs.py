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
    os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")
).resolve()

APP = PROJECT / "app"
DB = PROJECT / "data" / "phocap.db"
ROUTER = APP / "routers" / "surveys.py"
TEMPLATE = APP / "templates" / "surveys" / "year_records.html"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = (
    PROJECT
    / "exports"
    / f"backup_bai_13b_11_15_2_{STAMP}"
)

ROUTER_BACKUP = BACKUP / "app" / "routers" / "surveys.py"
TEMPLATE_BACKUP = (
    BACKUP
    / "app"
    / "templates"
    / "surveys"
    / "year_records.html"
)
DB_BACKUP = BACKUP / "data" / "phocap.db"

TABLE = "survey_person_year_records"

REQUIRED_COLUMNS = (
    "learning_status",
    "study_location_scope",
    "is_repeating_grade",
    "current_education_program",
    "completed_primary_program",
    "completed_lower_secondary_program",
)

PARAMS = (
    "study_location_scope",
    "is_repeating_grade",
    "current_education_program",
)

ROUTER_MARKER_START = (
    "# === BAI_13B_11_15_2_SAVE_PRIMARY_THCS_FIELDS_START ==="
)
ROUTER_MARKER_END = (
    "# === BAI_13B_11_15_2_SAVE_PRIMARY_THCS_FIELDS_END ==="
)

TEMPLATE_MARKER_START = (
    "{# === BAI_13B_11_15_2_PRIMARY_THCS_INPUT_START === #}"
)

JS_MARKER = "BAI_13B_11_15_2_PRIMARY_THCS_UI"


def read_text(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(f"Không tìm thấy: {path}")

    return path.read_text(
        encoding="utf-8-sig",
        errors="strict",
    )


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    path.write_text(
        value,
        encoding="utf-8",
    )


def backup_file(source: Path, target: Path) -> None:
    target.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    shutil.copy2(
        source,
        target,
    )


def sqlite_backup(source: Path, target: Path) -> None:
    target.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    src = sqlite3.connect(str(source))
    dst = sqlite3.connect(str(target))

    try:
        src.backup(dst)
        dst.commit()
    finally:
        dst.close()
        src.close()


def sqlite_restore(source: Path, target: Path) -> None:
    src = sqlite3.connect(str(source))
    dst = sqlite3.connect(str(target))

    try:
        src.backup(dst)
        dst.commit()
    finally:
        dst.close()
        src.close()


def db_snapshot() -> dict:
    conn = sqlite3.connect(str(DB))

    try:
        columns = {
            str(row[1])
            for row in conn.execute(
                f'PRAGMA table_info("{TABLE}")'
            ).fetchall()
        }

        if not columns:
            raise RuntimeError(
                f"Không tìm thấy bảng {TABLE}."
            )

        count = int(
            conn.execute(
                f'SELECT COUNT(*) FROM "{TABLE}"'
            ).fetchone()[0]
        )

        integrity = str(
            conn.execute(
                "PRAGMA integrity_check"
            ).fetchone()[0]
        )

        fk = len(
            conn.execute(
                "PRAGMA foreign_key_check"
            ).fetchall()
        )

        return {
            "columns": columns,
            "count": count,
            "integrity": integrity,
            "fk": fk,
        }

    finally:
        conn.close()


def find_save_function(
    source: str,
) -> ast.AsyncFunctionDef | ast.FunctionDef:
    tree = ast.parse(source)

    found = []

    for node in ast.walk(tree):
        if not isinstance(
            node,
            (
                ast.FunctionDef,
                ast.AsyncFunctionDef,
            ),
        ):
            continue

        decorators = "\n".join(
            ast.get_source_segment(source, dec) or ""
            for dec in node.decorator_list
        )

        if (
            "/nam-hoc/luu" in decorators
            and ".post" in decorators.lower()
        ):
            found.append(node)

    if len(found) != 1:
        names = [
            node.name
            for node in found
        ]

        raise RuntimeError(
            "Phải tìm thấy đúng 1 route POST /nam-hoc/luu "
            f"trong app/routers/surveys.py; hiện có "
            f"{len(found)}: {names}"
        )

    return found[0]


def find_record_name(
    function_text: str,
) -> str:
    patterns = (
        r'(?m)^\s*([A-Za-z_]\w*)\.learning_status\s*=',
        r'(?m)^\s*([A-Za-z_]\w*)\.completed_primary_program\s*=',
        r'(?m)^\s*([A-Za-z_]\w*)\.completed_lower_secondary_program\s*=',
        r'(?m)^\s*([A-Za-z_]\w*)\.school_name_reported\s*=',
    )

    for pattern in patterns:
        match = re.search(
            pattern,
            function_text,
        )

        if match:
            return match.group(1)

    raise RuntimeError(
        "Không xác định được biến SurveyPersonYearRecord "
        "trong route lưu năm học."
    )


def patch_signature(
    source: str,
    node: ast.AsyncFunctionDef | ast.FunctionDef,
) -> str:
    header_start = int(node.lineno) - 1

    if not node.body:
        raise RuntimeError(
            "Route lưu không có body."
        )

    body_start = int(node.body[0].lineno) - 1

    lines = source.splitlines(
        keepends=True
    )

    header_text = "".join(
        lines[
            header_start:
            body_start
        ]
    )

    missing = [
        name
        for name in PARAMS
        if not re.search(
            rf'\b{re.escape(name)}\b\s*:',
            header_text,
        )
    ]

    if not missing:
        return source

    close_index = None

    for index in range(
        body_start - 1,
        header_start - 1,
        -1,
    ):
        stripped = lines[index].strip()

        if not stripped:
            continue

        if re.search(
            r'\)\s*(?:->\s*[^:]+)?\s*:\s*$',
            stripped,
        ):
            close_index = index
            break

    if close_index is None:
        raise RuntimeError(
            "Không nhận diện được dòng đóng signature "
            "của route lưu năm học."
        )

    if close_index == header_start:
        raise RuntimeError(
            "Route lưu đang viết signature trên một dòng; "
            "bộ cài dừng để tránh sửa sai."
        )

    if "Annotated[" in header_text and "Form()" in header_text:
        param_lines = [
            (
                f"    {name}: "
                f"Annotated[str | None, Form()] = None,\n"
            )
            for name in missing
        ]
    elif "Form(" in header_text:
        param_lines = [
            (
                f"    {name}: "
                f"str | None = Form(None),\n"
            )
            for name in missing
        ]
    else:
        raise RuntimeError(
            "Không xác định được style Form() "
            "trong route lưu năm học."
        )

    lines[
        close_index:
        close_index
    ] = param_lines

    patched = "".join(lines)

    ast.parse(patched)

    return patched


def patch_save_logic(
    source: str,
) -> str:
    if ROUTER_MARKER_START in source:
        return source

    node = find_save_function(
        source
    )

    lines = source.splitlines(
        keepends=True
    )

    function_start = sum(
        len(item)
        for item in lines[
            : int(node.lineno) - 1
        ]
    )

    function_end = sum(
        len(item)
        for item in lines[
            : int(node.end_lineno)
        ]
    )

    function_text = source[
        function_start:
        function_end
    ]

    record = find_record_name(
        function_text
    )

    commit_matches = list(
        re.finditer(
            r'(?m)^(?P<indent>\s*)db\.commit\(\)\s*$',
            function_text,
        )
    )

    if not commit_matches:
        raise RuntimeError(
            "Không tìm thấy db.commit() trong route lưu năm học."
        )

    commit = commit_matches[0]
    indent = commit.group("indent")

    save_block = f'''{indent}{ROUTER_MARKER_START}
{indent}# Nơi học dùng chung Tiểu học + THCS.
{indent}if study_location_scope is not None:
{indent}    _b1512_location = str(
{indent}        study_location_scope or "CHUA_XAC_DINH"
{indent}    ).strip().upper()
{indent}    if _b1512_location not in {{
{indent}        "CHUA_XAC_DINH",
{indent}        "TAI_CHO",
{indent}        "DI_HOC_NOI_KHAC",
{indent}        "NOI_KHAC_DEN",
{indent}    }}:
{indent}        _b1512_location = "CHUA_XAC_DINH"
{indent}    {record}.study_location_scope = _b1512_location
{indent}
{indent}# Lưu ban dùng chung Tiểu học + THCS.
{indent}if is_repeating_grade is not None:
{indent}    _b1512_repeat = str(
{indent}        is_repeating_grade or "CHUA_XAC_DINH"
{indent}    ).strip().upper()
{indent}    if _b1512_repeat in {{"CO", "1", "TRUE"}}:
{indent}        {record}.is_repeating_grade = True
{indent}    elif _b1512_repeat in {{"KHONG", "0", "FALSE"}}:
{indent}        {record}.is_repeating_grade = False
{indent}    else:
{indent}        {record}.is_repeating_grade = None
{indent}
{indent}# Chương trình hiện tại chỉ do giao diện THCS gửi lên.
{indent}# Khi Tiểu học/nhóm khác không có field này, giữ nguyên dữ liệu.
{indent}if current_education_program is not None:
{indent}    _b1512_program = str(
{indent}        current_education_program or "CHUA_XAC_DINH"
{indent}    ).strip().upper()
{indent}    if _b1512_program not in {{
{indent}        "CHUA_XAC_DINH",
{indent}        "THPT",
{indent}        "GDTX",
{indent}        "GDNN",
{indent}        "KHAC",
{indent}    }}:
{indent}        _b1512_program = "CHUA_XAC_DINH"
{indent}    {record}.current_education_program = _b1512_program
{indent}
{indent}# Hai trạng thái này tái sử dụng learning_status hiện có.
{indent}_b1512_learning = str(
{indent}    learning_status or ""
{indent}).strip().upper()
{indent}if _b1512_learning in {{"BO_HOC", "CHUA_DI_HOC"}}:
{indent}    {record}.learning_status = _b1512_learning
{indent}{ROUTER_MARKER_END}
'''

    patched_function = (
        function_text[:commit.start()]
        + save_block
        + function_text[commit.start():]
    )

    patched = (
        source[:function_start]
        + patched_function
        + source[function_end:]
    )

    ast.parse(patched)

    return patched


def patch_router(
    source: str,
) -> str:
    node = find_save_function(
        source
    )

    source = patch_signature(
        source,
        node,
    )

    source = patch_save_logic(
        source
    )

    return source


def patch_learning_status_options(
    source: str,
) -> str:
    if (
        'value="BO_HOC"' in source
        and 'value="CHUA_DI_HOC"' in source
    ):
        return source

    pattern = re.compile(
        r'''(?is)
        <select\b
        (?=[^>]*(?:id|name)=["']learning_status["'])
        [^>]*>
        .*?
        </select>
        ''',
        re.X,
    )

    match = pattern.search(
        source
    )

    if not match:
        raise RuntimeError(
            "Không tìm thấy select learning_status "
            "trong year_records.html."
        )

    block = match.group(0)

    options = r'''
            <option
                value="BO_HOC"
                data-b1512-primary-thcs-status
                {% if selected_record and selected_record.learning_status == "BO_HOC" %}selected{% endif %}
            >
                Bỏ học
            </option>
            <option
                value="CHUA_DI_HOC"
                data-b1512-primary-thcs-status
                {% if selected_record and selected_record.learning_status == "CHUA_DI_HOC" %}selected{% endif %}
            >
                Chưa đi học
            </option>
'''

    block = block.replace(
        "</select>",
        options + "\n        </select>",
        1,
    )

    return (
        source[:match.start()]
        + block
        + source[match.end():]
    )


INPUT_BLOCK = r'''
{# === BAI_13B_11_15_2_PRIMARY_THCS_INPUT_START === #}
<div
    id="b1512_primary_thcs_fields"
    class="form-group full"
    hidden
    style="
        border:1px solid #cfe4d4;
        border-radius:14px;
        padding:16px;
        background:#f7fcf8;
        margin-top:14px;
    "
>
    <h3 style="margin:0 0 8px 0;">
        Thông tin phục vụ báo cáo Tiểu học / THCS
    </h3>

    <p style="margin:0 0 14px 0;color:#60758a;">
        Nhập dữ liệu gốc theo từng đối tượng.
        Các số liệu tổng hợp theo tuổi, lớp và chương trình
        sẽ do hệ thống tự tính.
    </p>

    <div class="form-grid">
        <div class="form-group">
            <label for="study_location_scope">
                Nơi học
            </label>

            {% set b1512_location =
                selected_record.study_location_scope
                if selected_record and selected_record.study_location_scope
                else "CHUA_XAC_DINH"
            %}

            <select
                id="study_location_scope"
                name="study_location_scope"
            >
                <option
                    value="CHUA_XAC_DINH"
                    {% if b1512_location == "CHUA_XAC_DINH" %}selected{% endif %}
                >
                    -- Chưa xác định --
                </option>

                <option
                    value="TAI_CHO"
                    {% if b1512_location == "TAI_CHO" %}selected{% endif %}
                >
                    Tại chỗ
                </option>

                <option
                    value="DI_HOC_NOI_KHAC"
                    {% if b1512_location == "DI_HOC_NOI_KHAC" %}selected{% endif %}
                >
                    Đi học nơi khác
                </option>

                <option
                    value="NOI_KHAC_DEN"
                    {% if b1512_location == "NOI_KHAC_DEN" %}selected{% endif %}
                >
                    Nơi khác đến
                </option>
            </select>
        </div>

        <div class="form-group">
            <label for="is_repeating_grade">
                Lưu ban
            </label>

            <select
                id="is_repeating_grade"
                name="is_repeating_grade"
            >
                <option
                    value="CHUA_XAC_DINH"
                    {% if not selected_record or selected_record.is_repeating_grade is none %}selected{% endif %}
                >
                    -- Chưa xác định --
                </option>

                <option
                    value="CO"
                    {% if selected_record and selected_record.is_repeating_grade is sameas true %}selected{% endif %}
                >
                    Có
                </option>

                <option
                    value="KHONG"
                    {% if selected_record and selected_record.is_repeating_grade is sameas false %}selected{% endif %}
                >
                    Không
                </option>
            </select>
        </div>

        <div
            id="b1512_program_wrap"
            class="form-group full"
            hidden
        >
            <label for="current_education_program">
                Chương trình đang học
            </label>

            {% set b1512_program =
                selected_record.current_education_program
                if selected_record and selected_record.current_education_program
                else "CHUA_XAC_DINH"
            %}

            <select
                id="current_education_program"
                name="current_education_program"
            >
                <option
                    value="CHUA_XAC_DINH"
                    {% if b1512_program == "CHUA_XAC_DINH" %}selected{% endif %}
                >
                    -- Chưa xác định --
                </option>

                <option
                    value="THPT"
                    {% if b1512_program == "THPT" %}selected{% endif %}
                >
                    Phổ thông / THPT
                </option>

                <option
                    value="GDTX"
                    {% if b1512_program == "GDTX" %}selected{% endif %}
                >
                    GDTX
                </option>

                <option
                    value="GDNN"
                    {% if b1512_program == "GDNN" %}selected{% endif %}
                >
                    GDNN
                </option>

                <option
                    value="KHAC"
                    {% if b1512_program == "KHAC" %}selected{% endif %}
                >
                    Khác
                </option>
            </select>

            <div style="margin-top:6px;color:#60758a;font-size:13px;">
                Mục này chỉ hiển thị đối với nhóm THCS;
                Tiểu học không nhập chương trình THPT/GDTX/GDNN.
            </div>
        </div>
    </div>
</div>
{# === BAI_13B_11_15_2_PRIMARY_THCS_INPUT_END === #}
'''


JS_BLOCK = r'''
<script>
(function () {
    // === BAI_13B_11_15_2_PRIMARY_THCS_UI ===
    const shared = document.getElementById(
        "b1512_primary_thcs_fields"
    );

    const programWrap = document.getElementById(
        "b1512_program_wrap"
    );

    const locationSelect = document.getElementById(
        "study_location_scope"
    );

    const repeatSelect = document.getElementById(
        "is_repeating_grade"
    );

    const programSelect = document.getElementById(
        "current_education_program"
    );

    const learningStatus = document.getElementById(
        "learning_status"
    ) || document.querySelector(
        'select[name="learning_status"]'
    );

    function visible(element) {
        if (!element) {
            return false;
        }

        if (element.hidden) {
            return false;
        }

        return element.offsetParent !== null;
    }

    function sync() {
        const primaryField = document.querySelector(
            '[name="completed_primary_program"]'
        );

        const secondaryField = document.querySelector(
            '[name="completed_lower_secondary_program"]'
        );

        const primaryVisible = visible(
            primaryField
        );

        const secondaryVisible = visible(
            secondaryField
        );

        const showShared = (
            primaryVisible
            || secondaryVisible
        );

        if (shared) {
            shared.hidden = !showShared;
        }

        if (locationSelect) {
            locationSelect.disabled = !showShared;
        }

        if (repeatSelect) {
            repeatSelect.disabled = !showShared;
        }

        if (programWrap) {
            programWrap.hidden = !secondaryVisible;
        }

        if (programSelect) {
            programSelect.disabled = !secondaryVisible;
        }

        if (learningStatus) {
            const extraOptions = learningStatus.querySelectorAll(
                "option[data-b1512-primary-thcs-status]"
            );

            extraOptions.forEach(function (option) {
                option.hidden = !showShared;
                option.disabled = !showShared;
            });
        }
    }

    sync();

    window.setTimeout(
        sync,
        0
    );

    window.setTimeout(
        sync,
        200
    );

    const observer = new MutationObserver(
        function () {
            sync();
        }
    );

    observer.observe(
        document.body,
        {
            attributes: true,
            subtree: true,
            attributeFilter: [
                "hidden",
                "style",
                "class"
            ]
        }
    );
})();
</script>
'''


def find_submit_anchor(
    source: str,
) -> int:
    patterns = (
        re.compile(
            r'(?is)<button\b[^>]*type=["\']submit["\'][^>]*>'
        ),
        re.compile(
            r'(?is)<button\b[^>]*>.*?Lưu thông tin năm học'
        ),
    )

    for pattern in patterns:
        match = pattern.search(
            source
        )

        if match:
            return match.start()

    raise RuntimeError(
        "Không tìm thấy nút submit của form năm học."
    )


def patch_template(
    source: str,
) -> str:
    if TEMPLATE_MARKER_START in source:
        if JS_MARKER not in source:
            raise RuntimeError(
                "Template có block Bài 15.2 nhưng thiếu JS; "
                "dừng để tránh cài chồng."
            )

        return source

    source = patch_learning_status_options(
        source
    )

    form_match = re.search(
        r'(?is)<form\b[^>]*id=["\']year_record_form["\'][^>]*>',
        source,
    )

    if not form_match:
        raise RuntimeError(
            "Không tìm thấy form id=year_record_form."
        )

    submit_pos = find_submit_anchor(
        source
    )

    if submit_pos <= form_match.end():
        raise RuntimeError(
            "Vị trí nút submit không nằm sau form năm học."
        )

    source = (
        source[:submit_pos]
        + INPUT_BLOCK
        + "\n"
        + source[submit_pos:]
    )

    if JS_MARKER not in source:
        body_close = source.rfind(
            "</body>"
        )

        if body_close < 0:
            raise RuntimeError(
                "Template thiếu </body>."
            )

        source = (
            source[:body_close]
            + JS_BLOCK
            + "\n"
            + source[body_close:]
        )

    return source


def verify_router(
    source: str,
) -> None:
    ast.parse(source)

    required = (
        ROUTER_MARKER_START,
        "study_location_scope",
        "is_repeating_grade",
        "current_education_program",
        '"BO_HOC"',
        '"CHUA_DI_HOC"',
    )

    for token in required:
        if token not in source:
            raise RuntimeError(
                "Router sau cài thiếu: "
                + token
            )


def verify_template(
    source: str,
) -> None:
    from jinja2 import Environment

    Environment().parse(
        source
    )

    required = (
        TEMPLATE_MARKER_START,
        'name="study_location_scope"',
        'name="is_repeating_grade"',
        'name="current_education_program"',
        'value="BO_HOC"',
        'value="CHUA_DI_HOC"',
        "Tại chỗ",
        "Đi học nơi khác",
        "Nơi khác đến",
        "Phổ thông / THPT",
        "GDTX",
        "GDNN",
        JS_MARKER,
    )

    for token in required:
        if token not in source:
            raise RuntimeError(
                "Template sau cài thiếu: "
                + token
            )


def compile_python(
    path: Path,
) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "py_compile",
            str(path),
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
            f"py_compile không đạt: {path}"
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


def main() -> int:
    print("=" * 132)
    print(
        "BÀI 13B-11.15.2 - "
        "NỐI DỮ LIỆU TIỂU HỌC + THCS VÀO THÔNG TIN NĂM HỌC"
    )
    print("=" * 132)
    print()
    print("TIỂU HỌC:")
    print(
        " - Tình trạng học tập bổ sung: Bỏ học / Chưa đi học."
    )
    print(
        " - Nơi học: Tại chỗ / Đi học nơi khác / Nơi khác đến."
    )
    print(
        " - Lưu ban: Có / Không / Chưa xác định."
    )
    print(
        " - KHÔNG hiển thị chương trình THPT/GDTX/GDNN."
    )
    print()
    print("THCS:")
    print(
        " - Có toàn bộ dữ liệu như Tiểu học."
    )
    print(
        " - Thêm Chương trình: THPT / GDTX / GDNN / Khác."
    )
    print()
    print("NGUYÊN TẮC:")
    print(
        " - Không tạo cột Bỏ học/Chưa đi học riêng."
    )
    print(
        " - BO_HOC và CHUA_DI_HOC dùng learning_status hiện có."
    )
    print(
        " - Các field chỉ submit khi đúng khối Tiểu học/THCS đang hiển thị."
    )
    print(
        " - Không sửa dữ liệu cũ khi cài."
    )
    print(
        " - Chưa sửa logic hoàn thành phiếu/báo cáo ở Bài này."
    )
    print()
    print("AN TOÀN:")
    print(
        " - Kiểm tra đủ schema Bài 15.1."
    )
    print(
        " - Backup router/template/database."
    )
    print(
        " - py_compile + Jinja + integrity + foreign key."
    )
    print(
        " - Có lỗi tự rollback."
    )
    print()

    for path in (
        DB,
        ROUTER,
        TEMPLATE,
    ):
        if not path.exists():
            raise RuntimeError(
                f"Không tìm thấy: {path}"
            )

    before = db_snapshot()

    missing = [
        column
        for column in REQUIRED_COLUMNS
        if column
        not in before["columns"]
    ]

    if missing:
        raise RuntimeError(
            "Thiếu schema nền Bài 13B-11.15.1: "
            + ", ".join(
                missing
            )
        )

    if (
        before["integrity"].lower()
        != "ok"
        or before["fk"] != 0
    ):
        raise RuntimeError(
            "Database không đạt kiểm tra an toàn trước cài."
        )

    print(
        "integrity_check trước cài:",
        before["integrity"],
    )
    print(
        "foreign_key_check trước cài:",
        before["fk"],
        "lỗi",
    )
    print(
        "survey_person_year_records:",
        before["count"],
        "bản ghi",
    )

    router_before = read_text(
        ROUTER
    )

    template_before = read_text(
        TEMPLATE
    )

    for token in (
        "completed_primary_program",
        "completed_lower_secondary_program",
        "learning_status",
    ):
        if token not in template_before:
            raise RuntimeError(
                "Template thiếu nền cấp học: "
                + token
            )

    BACKUP.mkdir(
        parents=True,
        exist_ok=False,
    )

    backup_file(
        ROUTER,
        ROUTER_BACKUP,
    )
    backup_file(
        TEMPLATE,
        TEMPLATE_BACKUP,
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
        router_after = patch_router(
            router_before
        )

        template_after = patch_template(
            template_before
        )

        verify_router(
            router_after
        )

        verify_template(
            template_after
        )

        write_text(
            ROUTER,
            router_after,
        )

        write_text(
            TEMPLATE,
            template_after,
        )

        compile_python(
            ROUTER
        )

        after = db_snapshot()

        if after["count"] != before["count"]:
            raise RuntimeError(
                "Số bản ghi survey_person_year_records "
                "bị thay đổi khi cài."
            )

        if after["columns"] != before["columns"]:
            raise RuntimeError(
                "Bài 15.2 không được thay đổi schema database."
            )

        if after["integrity"].lower() != "ok":
            raise RuntimeError(
                "integrity_check sau cài không OK."
            )

        if after["fk"] != 0:
            raise RuntimeError(
                "foreign_key_check sau cài "
                f"có {after['fk']} lỗi."
            )

        clear_cache()

        print()
        print("KIỂM TRA SAU CÀI:")
        print(
            " - Tiểu học: Nơi học + Lưu ban: ĐÃ BỔ SUNG"
        )
        print(
            " - Tiểu học: Chương trình THPT/GDTX/GDNN: KHÔNG HIỂN THỊ"
        )
        print(
            " - THCS: Nơi học + Lưu ban: ĐÃ BỔ SUNG"
        )
        print(
            " - THCS: Chương trình THPT/GDTX/GDNN/Khác: ĐÃ BỔ SUNG"
        )
        print(
            " - learning_status Bỏ học: ĐÃ BỔ SUNG LỰA CHỌN"
        )
        print(
            " - learning_status Chưa đi học: ĐÃ BỔ SUNG LỰA CHỌN"
        )
        print(
            " - MN/XMC/nhóm khác: field TH/THCS tự ẩn và disable"
        )
        print(
            " - Database: KHÔNG THAY ĐỔI DỮ LIỆU/SCHEMA"
        )
        print(
            " - py_compile router: OK"
        )
        print(
            " - Jinja parse: OK"
        )
        print(
            " - integrity_check: OK"
        )
        print(
            " - foreign_key_check: 0 lỗi"
        )
        print()
        print("=" * 132)
        print(
            "CÀI ĐẶT BÀI 13B-11.15.2 THÀNH CÔNG"
        )
        print("=" * 132)

        return 0

    except Exception:
        traceback.print_exc()

        print()
        print(
            "CÓ LỖI - ĐANG KHÔI PHỤC ROUTER/TEMPLATE/DATABASE..."
        )

        try:
            shutil.copy2(
                ROUTER_BACKUP,
                ROUTER,
            )
            print(
                " - Đã khôi phục router."
            )
        except Exception as exc:
            print(
                " - Lỗi khôi phục router:",
                exc,
            )

        try:
            shutil.copy2(
                TEMPLATE_BACKUP,
                TEMPLATE,
            )
            print(
                " - Đã khôi phục template."
            )
        except Exception as exc:
            print(
                " - Lỗi khôi phục template:",
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
