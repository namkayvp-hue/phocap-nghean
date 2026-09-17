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
MODEL = APP / "staff_models.py"
ROUTER = APP / "routers" / "report_inputs.py"
TEMPLATE = APP / "templates" / "report_inputs" / "gv_mn01.html"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = (
    PROJECT
    / "exports"
    / f"backup_bai_13b_11_14_7_2_{STAMP}"
)

DB_BACKUP = BACKUP / "data" / "phocap.db"
MODEL_BACKUP = BACKUP / "app" / "staff_models.py"
ROUTER_BACKUP = BACKUP / "app" / "routers" / "report_inputs.py"
TEMPLATE_BACKUP = BACKUP / "app" / "templates" / "report_inputs" / "gv_mn01.html"

TABLE = "staff_year_records"

NEW_COLUMNS = (
    "teaches_multigrade",
    "uses_multigrade_program_4yo",
    "uses_multigrade_program_5yo",
)

MODEL_MARKER_START = "# === BAI_13B_11_14_7_2_MULTIGRADE_MODEL_START ==="
MODEL_MARKER_END = "# === BAI_13B_11_14_7_2_MULTIGRADE_MODEL_END ==="

ROUTER_HELPER_MARKER = "# === BAI_13B_11_14_7_2_HELPER_START ==="
ROUTER_SAVE_MARKER = "# === BAI_13B_11_14_7_2_SAVE_MULTIGRADE_START ==="
ROUTER_CSVC_MARKER = "# === BAI_13B_11_14_7_2_CSVC_CLASS_SOURCE_START ==="

TEMPLATE_MARKER_START = "{# === BAI_13B_11_14_7_2_MN01GV_START === #}"
TEMPLATE_MARKER_END = "{# === BAI_13B_11_14_7_2_MN01GV_END === #}"


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
    shutil.copy2(source, target)


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


def db_connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB))
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def table_exists(
    conn: sqlite3.Connection,
    table: str,
) -> bool:
    return (
        conn.execute(
            '''
            SELECT 1
            FROM sqlite_master
            WHERE type='table'
              AND name=?
            LIMIT 1
            ''',
            (table,),
        ).fetchone()
        is not None
    )


def table_columns(
    conn: sqlite3.Connection,
    table: str,
) -> list[str]:
    return [
        str(row[1])
        for row in conn.execute(
            f'PRAGMA table_info("{table}")'
        ).fetchall()
    ]


def table_count(
    conn: sqlite3.Connection,
    table: str,
) -> int:
    return int(
        conn.execute(
            f'SELECT COUNT(*) FROM "{table}"'
        ).fetchone()[0]
    )


def db_health(
    conn: sqlite3.Connection,
) -> tuple[str, int]:
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

    return integrity, fk


def snapshot_db() -> dict:
    conn = db_connect()

    try:
        if not table_exists(conn, TABLE):
            raise RuntimeError(
                f"Không có bảng {TABLE}"
            )

        integrity, fk = db_health(conn)

        result = {
            "integrity": integrity,
            "fk": fk,
            "staff_count": table_count(
                conn,
                TABLE,
            ),
            "staff_columns": table_columns(
                conn,
                TABLE,
            ),
        }

        if table_exists(
            conn,
            "school_mn01_csvc_inputs",
        ):
            result["csvc_count"] = table_count(
                conn,
                "school_mn01_csvc_inputs",
            )
        else:
            result["csvc_count"] = None

        return result

    finally:
        conn.close()


def ensure_db_columns() -> list[str]:
    added: list[str] = []

    conn = db_connect()

    try:
        current = set(
            table_columns(
                conn,
                TABLE,
            )
        )

        for column in NEW_COLUMNS:
            if column in current:
                continue

            sql = (
                f'ALTER TABLE "{TABLE}" '
                f'ADD COLUMN "{column}" BOOLEAN'
            )

            conn.execute(sql)
            added.append(column)

        conn.commit()

    finally:
        conn.close()

    return added


def find_staff_year_class(source: str) -> ast.ClassDef:
    tree = ast.parse(source)

    candidates: list[ast.ClassDef] = []

    for node in tree.body:
        if not isinstance(
            node,
            ast.ClassDef,
        ):
            continue

        table_name = None

        for stmt in node.body:
            if not isinstance(
                stmt,
                (
                    ast.Assign,
                    ast.AnnAssign,
                ),
            ):
                continue

            targets = (
                stmt.targets
                if isinstance(
                    stmt,
                    ast.Assign,
                )
                else [stmt.target]
            )

            for target in targets:
                if (
                    isinstance(
                        target,
                        ast.Name,
                    )
                    and target.id
                    == "__tablename__"
                ):
                    value = getattr(
                        stmt,
                        "value",
                        None,
                    )

                    if (
                        isinstance(
                            value,
                            ast.Constant,
                        )
                        and isinstance(
                            value.value,
                            str,
                        )
                    ):
                        table_name = (
                            value.value
                        )

        if table_name == TABLE:
            candidates.append(node)

    if len(candidates) != 1:
        raise RuntimeError(
            "Phải tìm thấy đúng 1 model "
            f'{TABLE}; hiện có {len(candidates)}.'
        )

    return candidates[0]


def clone_boolean_rest(
    class_text: str,
) -> tuple[str, str]:
    for field in (
        "receives_policy",
        "is_active",
    ):
        pattern = re.compile(
            rf"^(?P<indent>\s*)"
            rf"{re.escape(field)}"
            rf"(?P<rest>\s*(?::[^=]+)?=\s*.+)$",
            flags=re.M,
        )

        match = pattern.search(
            class_text
        )

        if (
            match
            and "Boolean"
            in match.group("rest")
        ):
            return (
                match.group("indent"),
                match.group("rest"),
            )

    raise RuntimeError(
        "Không tìm thấy field Boolean "
        "trong StaffYearRecord để dùng đúng style model hiện tại."
    )


def patch_model(source: str) -> str:
    node = find_staff_year_class(source)

    class_lines = source.splitlines(
        keepends=True
    )

    start = int(node.lineno) - 1
    end = int(node.end_lineno)

    class_text = "".join(
        class_lines[start:end]
    )

    missing = [
        field
        for field in NEW_COLUMNS
        if not re.search(
            rf"(?m)^\s*{re.escape(field)}(?:\s*:|\s*=)",
            class_text,
        )
    ]

    if not missing:
        return source

    indent, rest = clone_boolean_rest(
        class_text
    )

    insert_after = None

    for field in (
        "receives_policy",
        "professional_standard",
        "qualification_standard",
    ):
        for index in range(
            start,
            end,
        ):
            if re.match(
                rf"^\s*{re.escape(field)}(?:\s*:|\s*=)",
                class_lines[index],
            ):
                insert_after = index
                break

        if insert_after is not None:
            break

    if insert_after is None:
        raise RuntimeError(
            "Không xác định được vị trí an toàn "
            "để chèn field lớp ghép vào StaffYearRecord."
        )

    block = (
        f"{indent}{MODEL_MARKER_START}\n"
        + "".join(
            f"{indent}{field}{rest}\n"
            for field in missing
        )
        + f"{indent}{MODEL_MARKER_END}\n"
    )

    class_lines.insert(
        insert_after + 1,
        block,
    )

    patched = "".join(
        class_lines
    )

    ast.parse(patched)

    return patched


def patch_router_helper(source: str) -> str:
    if ROUTER_HELPER_MARKER in source:
        return source

    anchor = (
        '@router.get("/doi-ngu/nhap-mn-01-gv", '
        "response_class=HTMLResponse)"
    )

    if anchor not in source:
        raise RuntimeError(
            "Không tìm thấy route GET "
            "/doi-ngu/nhap-mn-01-gv."
        )

    block = r'''
# === BAI_13B_11_14_7_2_HELPER_START ===
def _b1472_optional_bool(value: Any) -> bool | None:
    raw = str(value or "").strip().upper()

    if raw in {"CO", "1", "TRUE", "YES", "ON"}:
        return True

    if raw in {"KHONG", "0", "FALSE", "NO", "OFF"}:
        return False

    return None
# === BAI_13B_11_14_7_2_HELPER_END ===


'''

    return source.replace(
        anchor,
        block + anchor,
        1,
    )


def patch_router_get_csvc(source: str) -> str:
    if ROUTER_CSVC_MARKER in source:
        return source

    route_start = source.find(
        '@router.get("/doi-ngu/nhap-mn-01-gv"'
    )

    route_end = source.find(
        '@router.post("/doi-ngu/nhap-mn-01-gv")',
        route_start,
    )

    if (
        route_start < 0
        or route_end < 0
    ):
        raise RuntimeError(
            "Không xác định được khối GET MN-01-GV."
        )

    route = source[
        route_start:
        route_end
    ]

    declaration_anchor = (
        "    class_summary = None\n"
        "    network_reference: dict[str, Any] = {}\n"
    )

    if declaration_anchor not in route:
        raise RuntimeError(
            "Không tìm thấy vị trí khai báo "
            "class_summary trong GET MN-01-GV."
        )

    route = route.replace(
        declaration_anchor,
        (
            "    class_summary = None\n"
            "    csvc_record = None\n"
            "    network_reference: dict[str, Any] = {}\n"
        ),
        1,
    )

    load_anchor = r'''        class_summary = db.scalar(
            select(SchoolStaffYearSummary).where(
                SchoolStaffYearSummary.school_id == selected_school_id_int,
                SchoolStaffYearSummary.school_year_id == selected_year_id,
            )
        )
'''

    if load_anchor not in route:
        raise RuntimeError(
            "Không tìm thấy block nạp class_summary "
            "trong GET MN-01-GV."
        )

    load_replacement = load_anchor + r'''
        csvc_record = db.scalar(
            select(SchoolMn01CsvcInput).where(
                SchoolMn01CsvcInput.school_id == selected_school_id_int,
                SchoolMn01CsvcInput.school_year_id == selected_year_id,
            )
        )
'''

    route = route.replace(
        load_anchor,
        load_replacement,
        1,
    )

    class_pattern = re.compile(
        r'''    class_prefill = \{
.*?
    \}

    ethnic_prefill = \(''',
        flags=re.S,
    )

    match = class_pattern.search(
        route
    )

    if not match:
        raise RuntimeError(
            "Không tìm thấy block class_prefill "
            "trong GET MN-01-GV."
        )

    class_replacement = r'''    # === BAI_13B_11_14_7_2_CSVC_CLASS_SOURCE_START ===
    # Số nhóm/lớp trong MN-01-GV chỉ đọc từ phân hệ CSVC.
    # Không nhập lại số lớp tại Đội ngũ.
    csvc_has_data = csvc_record is not None

    csvc_nursery_groups = (
        int(csvc_record.nursery_group_count or 0)
        if csvc_record is not None
        else 0
    )

    csvc_preschool_3_4 = (
        int(csvc_record.preschool_class_3_4_count or 0)
        if csvc_record is not None
        else 0
    )

    csvc_preschool_5 = (
        int(csvc_record.preschool_class_5_count or 0)
        if csvc_record is not None
        else 0
    )

    class_prefill = {
        "institution_group": (
            class_summary.institution_group
            if class_summary
            else _mn_institution_group(selected_school)
        ),
        "total_groups_classes": (
            csvc_nursery_groups
            + csvc_preschool_3_4
            + csvc_preschool_5
        ),
        "preschool_classes_3_4": csvc_preschool_3_4,
        "preschool_classes_5": csvc_preschool_5,
    }
    # === BAI_13B_11_14_7_2_CSVC_CLASS_SOURCE_END ===

    ethnic_prefill = ('''

    route = (
        route[:match.start()]
        + class_replacement
        + route[match.end():]
    )

    context_anchor = (
        '            "class_prefill": class_prefill,\n'
    )

    if context_anchor not in route:
        raise RuntimeError(
            "Không tìm thấy context class_prefill."
        )

    route = route.replace(
        context_anchor,
        (
            context_anchor
            + '            "csvc_record": csvc_record,\n'
            + '            "csvc_has_data": csvc_has_data,\n'
        ),
        1,
    )

    patched = (
        source[:route_start]
        + route
        + source[route_end:]
    )

    ast.parse(
        patched
    )

    return patched


def patch_router_post(source: str) -> str:
    post_start = source.find(
        '@router.post("/doi-ngu/nhap-mn-01-gv")'
    )

    if post_start < 0:
        raise RuntimeError(
            "Không tìm thấy POST MN-01-GV."
        )

    next_route = source.find(
        "\n@router.",
        post_start + 20,
    )

    if next_route < 0:
        next_route = len(source)

    post = source[
        post_start:
        next_route
    ]

    class_block_pattern = re.compile(
        r'''    class_summary = db\.scalar\(
.*?
    class_summary\.updated_by_user_id = int\(\(user or \{\}\)\.get\("id"\) or 0\) or None

''',
        flags=re.S,
    )

    class_match = class_block_pattern.search(
        post
    )

    if class_match:
        post = (
            post[:class_match.start()]
            + '''    # Bài 13B-11.14.7.2:
    # Cơ sở/nhóm/lớp là nguồn của CSVC.
    # MN-01-GV không ghi lại dữ liệu lớp ở đây.

'''
            + post[class_match.end():]
        )

    if ROUTER_SAVE_MARKER not in post:
        anchor = (
            '        row.receives_policy = '
            'str(form.get(prefix + "policy") or "0") == "1"\n'
        )

        if anchor not in post:
            raise RuntimeError(
                "Không tìm thấy dòng lưu "
                "receives_policy trong POST MN-01-GV."
            )

        save_block = r'''        # === BAI_13B_11_14_7_2_SAVE_MULTIGRADE_START ===
        if (
            str(row.position_group or "").strip().upper()
            == "GIAO_VIEN"
            and prefix + "multigrade" in form
        ):
            _b1472_multigrade = _b1472_optional_bool(
                form.get(prefix + "multigrade")
            )

            row.teaches_multigrade = _b1472_multigrade

            if _b1472_multigrade is True:
                row.uses_multigrade_program_4yo = (
                    _b1472_optional_bool(
                        form.get(prefix + "program_4yo")
                    )
                )

                row.uses_multigrade_program_5yo = (
                    _b1472_optional_bool(
                        form.get(prefix + "program_5yo")
                    )
                )
            else:
                row.uses_multigrade_program_4yo = None
                row.uses_multigrade_program_5yo = None
        # === BAI_13B_11_14_7_2_SAVE_MULTIGRADE_END ===
'''

        post = post.replace(
            anchor,
            anchor + save_block,
            1,
        )

    patched = (
        source[:post_start]
        + post
        + source[next_route:]
    )

    ast.parse(patched)

    return patched


def patch_router(source: str) -> str:
    source = patch_router_helper(
        source
    )
    source = patch_router_get_csvc(
        source
    )
    source = patch_router_post(
        source
    )
    return source


SECTION_1_NEW = r'''            <section class="panel" id="thong-tin-truong">
                <h2 class="section-title">
                    1. Thông tin cấp trường và tham chiếu CSVC
                </h2>

                {% if csvc_has_data %}
                <div class="notice notice-ok">
                    ✓ Số nhóm/lớp dưới đây được lấy trực tiếp từ
                    <strong>CSVC → Nhóm/lớp và phòng học</strong>.
                    Màn Đội ngũ không nhập lại số lớp.
                </div>
                {% else %}
                <div class="notice notice-ref">
                    Chưa có dữ liệu CSVC của trường/năm học này.
                    Hãy nhập tại <strong>CSVC → Nhóm/lớp và phòng học</strong>;
                    MN-01-GV sẽ tự lấy số lớp để tính tỷ lệ GV/lớp.
                </div>
                {% endif %}

                <div class="grid">
                    <div class="field">
                        <label>Loại cơ sở</label>
                        <input
                            type="text"
                            value="{{ institution_group_labels.get(class_prefill.institution_group, class_prefill.institution_group) }}"
                            readonly
                        >
                    </div>

                    <div class="field">
                        <label>Tổng số nhóm/lớp từ CSVC</label>
                        <input
                            type="number"
                            value="{{ class_prefill.total_groups_classes }}"
                            readonly
                        >
                    </div>

                    <div class="field">
                        <label>Số lớp mẫu giáo 3–4 tuổi từ CSVC</label>
                        <input
                            type="number"
                            value="{{ class_prefill.preschool_classes_3_4 }}"
                            readonly
                        >
                    </div>

                    <div class="field">
                        <label>Số lớp mẫu giáo 5 tuổi từ CSVC</label>
                        <input
                            type="number"
                            value="{{ class_prefill.preschool_classes_5 }}"
                            readonly
                        >
                    </div>

                    <div class="field">
                        <label>Số CBQL/GV/NV dân tộc thiểu số</label>
                        <input
                            type="number"
                            min="0"
                            name="ethnic_staff_count"
                            value="{{ ethnic_prefill }}"
                            {% if not can_edit %}readonly{% endif %}
                        >
                    </div>

                    <div class="field">
                        <label>Ghi chú báo cáo</label>
                        <textarea
                            name="notes"
                            {% if not can_edit %}readonly{% endif %}
                        >{{ extra.notes if extra and extra.notes else '' }}</textarea>
                    </div>
                </div>
            </section>
'''


def patch_template_section_1(source: str) -> str:
    pattern = re.compile(
        r'''            <section class="panel" id="thong-tin-truong">
.*?
            </section>

            <section class="panel" id="danh-sach-nhan-su">''',
        flags=re.S,
    )

    match = pattern.search(
        source
    )

    if not match:
        raise RuntimeError(
            "Không tìm thấy mục 1. Thông tin cấp trường "
            "trong gv_mn01.html."
        )

    replacement = (
        SECTION_1_NEW
        + '\n            <section class="panel" id="danh-sach-nhan-su">'
    )

    return (
        source[:match.start()]
        + replacement
        + source[match.end():]
    )


def patch_template_list(source: str) -> str:
    list_start = source.find(
        '<section class="panel" id="danh-sach-nhan-su">'
    )

    list_end = source.find(
        '<section class="panel" id="ra-soat">',
        list_start,
    )

    if (
        list_start < 0
        or list_end < 0
    ):
        raise RuntimeError(
            "Không xác định được bảng Danh sách nhân sự."
        )

    block = source[
        list_start:
        list_end
    ]

    header_anchor = '''                                <th>Đánh giá viên chức</th>
                                <th>Trạng thái</th>'''

    if header_anchor not in block:
        raise RuntimeError(
            "Không tìm thấy cột Đánh giá/Trạng thái "
            "trong bảng danh sách nhân sự."
        )

    block = block.replace(
        header_anchor,
        '''                                <th>Đánh giá viên chức</th>
                                <th>Dạy lớp ghép</th>
                                <th>CT 4 tuổi</th>
                                <th>CT 5 tuổi</th>
                                <th>Trạng thái</th>''',
        1,
    )

    row_anchor = '''                                <td>{{ r.staff_evaluation or '—' }}</td>
                                <td>{{ r.source_status_label or status_labels.get(r.status_code, r.status_code or '—') }}</td>'''

    if row_anchor not in block:
        raise RuntimeError(
            "Không tìm thấy dòng dữ liệu Đánh giá/Trạng thái."
        )

    row_new = r'''                                <td>{{ r.staff_evaluation or '—' }}</td>

                                {% if r.position_group == 'GIAO_VIEN' %}
                                <td>
                                    {% if r.teaches_multigrade is sameas true %}
                                    Có
                                    {% elif r.teaches_multigrade is sameas false %}
                                    Không
                                    {% else %}
                                    Chưa xác định
                                    {% endif %}
                                </td>
                                <td>
                                    {% if r.teaches_multigrade is sameas true %}
                                        {% if r.uses_multigrade_program_4yo is sameas true %}
                                        Có
                                        {% elif r.uses_multigrade_program_4yo is sameas false %}
                                        Không
                                        {% else %}
                                        Chưa xác định
                                        {% endif %}
                                    {% else %}
                                    —
                                    {% endif %}
                                </td>
                                <td>
                                    {% if r.teaches_multigrade is sameas true %}
                                        {% if r.uses_multigrade_program_5yo is sameas true %}
                                        Có
                                        {% elif r.uses_multigrade_program_5yo is sameas false %}
                                        Không
                                        {% else %}
                                        Chưa xác định
                                        {% endif %}
                                    {% else %}
                                    —
                                    {% endif %}
                                </td>
                                {% else %}
                                <td>—</td>
                                <td>—</td>
                                <td>—</td>
                                {% endif %}

                                <td>{{ r.source_status_label or status_labels.get(r.status_code, r.status_code or '—') }}</td>'''

    block = block.replace(
        row_anchor,
        row_new,
        1,
    )

    block = block.replace(
        '<tr><td colspan="9" class="muted">',
        '<tr><td colspan="12" class="muted">',
        1,
    )

    return (
        source[:list_start]
        + block
        + source[list_end:]
    )


def patch_template_review(source: str) -> str:
    review_start = source.find(
        '<section class="panel" id="ra-soat">'
    )

    if review_start < 0:
        raise RuntimeError(
            "Không tìm thấy mục Rà soát chỉ tiêu."
        )

    review_end = source.find(
        "{% if can_edit %}",
        review_start,
    )

    if review_end < 0:
        raise RuntimeError(
            "Không xác định được cuối mục Rà soát."
        )

    block = source[
        review_start:
        review_end
    ]

    header_anchor = '''                                    <th>STT</th><th>Họ và tên</th><th>Hình thức</th><th>Dạy nhóm/lớp</th>
                                    <th>Trình độ</th><th>Mức chuẩn</th><th>Chuẩn nghề nghiệp</th><th>Hưởng CĐ/CS</th>'''

    if header_anchor not in block:
        raise RuntimeError(
            "Không tìm thấy header bảng rà soát MN-01-GV."
        )

    block = block.replace(
        header_anchor,
        '''                                    <th>STT</th><th>Họ và tên</th><th>Hình thức</th><th>Dạy nhóm/lớp</th>
                                    <th>Dạy lớp ghép</th><th>CT 4 tuổi</th><th>CT 5 tuổi</th>
                                    <th>Trình độ</th><th>Mức chuẩn</th><th>Chuẩn nghề nghiệp</th><th>Hưởng CĐ/CS</th>''',
        1,
    )

    age_anchor = '''                                    <td><select class="mini-select" name="staff_{{ r.id }}_age_group" {% if not can_edit %}disabled{% endif %}>{% for code,label in teaching_age_labels.items() %}<option value="{{ code }}" {% if r.teaching_age_group == code %}selected{% endif %}>{{ label }}</option>{% endfor %}</select></td>
'''

    if age_anchor not in block:
        raise RuntimeError(
            "Không tìm thấy cột Dạy nhóm/lớp "
            "trong bảng rà soát."
        )

    multigrade_html = r'''                                    {% if r.position_group == 'GIAO_VIEN' %}
                                    <td>
                                        <select
                                            class="mini-select"
                                            name="staff_{{ r.id }}_multigrade"
                                            data-multigrade-master
                                            {% if not can_edit %}disabled{% endif %}
                                        >
                                            <option
                                                value="CHUA_XAC_DINH"
                                                {% if r.teaches_multigrade is none %}selected{% endif %}
                                            >
                                                -- Chưa xác định --
                                            </option>
                                            <option
                                                value="CO"
                                                {% if r.teaches_multigrade is sameas true %}selected{% endif %}
                                            >
                                                Có
                                            </option>
                                            <option
                                                value="KHONG"
                                                {% if r.teaches_multigrade is sameas false %}selected{% endif %}
                                            >
                                                Không
                                            </option>
                                        </select>
                                    </td>

                                    <td>
                                        <span data-multigrade-program-wrap>
                                            <select
                                                class="mini-select"
                                                name="staff_{{ r.id }}_program_4yo"
                                                data-multigrade-program
                                                {% if not can_edit %}disabled{% endif %}
                                            >
                                                <option
                                                    value="CHUA_XAC_DINH"
                                                    {% if r.uses_multigrade_program_4yo is none %}selected{% endif %}
                                                >
                                                    -- Chưa xác định --
                                                </option>
                                                <option
                                                    value="CO"
                                                    {% if r.uses_multigrade_program_4yo is sameas true %}selected{% endif %}
                                                >
                                                    Có
                                                </option>
                                                <option
                                                    value="KHONG"
                                                    {% if r.uses_multigrade_program_4yo is sameas false %}selected{% endif %}
                                                >
                                                    Không
                                                </option>
                                            </select>
                                        </span>
                                    </td>

                                    <td>
                                        <span data-multigrade-program-wrap>
                                            <select
                                                class="mini-select"
                                                name="staff_{{ r.id }}_program_5yo"
                                                data-multigrade-program
                                                {% if not can_edit %}disabled{% endif %}
                                            >
                                                <option
                                                    value="CHUA_XAC_DINH"
                                                    {% if r.uses_multigrade_program_5yo is none %}selected{% endif %}
                                                >
                                                    -- Chưa xác định --
                                                </option>
                                                <option
                                                    value="CO"
                                                    {% if r.uses_multigrade_program_5yo is sameas true %}selected{% endif %}
                                                >
                                                    Có
                                                </option>
                                                <option
                                                    value="KHONG"
                                                    {% if r.uses_multigrade_program_5yo is sameas false %}selected{% endif %}
                                                >
                                                    Không
                                                </option>
                                            </select>
                                        </span>
                                    </td>
                                    {% else %}
                                    <td class="muted">—</td>
                                    <td class="muted">—</td>
                                    <td class="muted">—</td>
                                    {% endif %}
'''

    block = block.replace(
        age_anchor,
        age_anchor + multigrade_html,
        1,
    )

    return (
        source[:review_start]
        + block
        + source[review_end:]
    )


def patch_template_script(source: str) -> str:
    if "BAI_13B_11_14_7_2_MULTIGRADE_UI" in source:
        return source

    anchor = "</body>"

    if anchor not in source:
        raise RuntimeError(
            "Template thiếu </body>."
        )

    script = r'''
<script>
(function () {
    // === BAI_13B_11_14_7_2_MULTIGRADE_UI ===
    const masters = document.querySelectorAll(
        'select[data-multigrade-master]'
    );

    masters.forEach(function (master) {
        const name = master.getAttribute('name') || '';
        const suffix = '_multigrade';

        if (!name.endsWith(suffix)) {
            return;
        }

        const prefix = name.slice(
            0,
            name.length - suffix.length
        );

        const program4 = document.querySelector(
            'select[name="' + prefix + '_program_4yo"]'
        );

        const program5 = document.querySelector(
            'select[name="' + prefix + '_program_5yo"]'
        );

        function syncPrograms() {
            const show = (
                master.value === 'CO'
            );

            [program4, program5].forEach(
                function (select) {
                    if (!select) {
                        return;
                    }

                    const wrap = select.closest(
                        '[data-multigrade-program-wrap]'
                    );

                    if (wrap) {
                        wrap.style.display = (
                            show
                                ? ''
                                : 'none'
                        );
                    }

                    if (!master.disabled) {
                        select.disabled = !show;
                    }
                }
            );
        }

        master.addEventListener(
            'change',
            syncPrograms
        );

        syncPrograms();
    });
})();
</script>
'''

    return source.replace(
        anchor,
        script + "\n" + anchor,
        1,
    )


def patch_template(source: str) -> str:
    if (
        TEMPLATE_MARKER_START
        in source
        and "data-multigrade-master"
        in source
    ):
        return source

    source = patch_template_section_1(
        source
    )
    source = patch_template_list(
        source
    )
    source = patch_template_review(
        source
    )
    source = patch_template_script(
        source
    )

    marker_anchor = (
        '<section class="panel" id="thong-tin-truong">'
    )

    source = source.replace(
        marker_anchor,
        (
            TEMPLATE_MARKER_START
            + "\n"
            + marker_anchor
        ),
        1,
    )

    closing_anchor = "</main>"

    source = source.replace(
        closing_anchor,
        (
            TEMPLATE_MARKER_END
            + "\n"
            + closing_anchor
        ),
        1,
    )

    return source


def compile_python(path: Path) -> None:
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


def verify_template(source: str) -> None:
    from jinja2 import Environment

    Environment().parse(
        source
    )

    required = (
        TEMPLATE_MARKER_START,
        "Dạy lớp ghép",
        "CT 4 tuổi",
        "CT 5 tuổi",
        "data-multigrade-master",
        "CSVC → Nhóm/lớp và phòng học",
    )

    for marker in required:
        if marker not in source:
            raise RuntimeError(
                "Template sau cài thiếu: "
                + marker
            )

    forbidden_names = (
        'name="total_groups_classes"',
        'name="preschool_classes_3_4"',
        'name="preschool_classes_5"',
        'name="institution_group"',
    )

    for item in forbidden_names:
        if item in source:
            raise RuntimeError(
                "MN-01-GV vẫn còn ô nhập trùng CSVC: "
                + item
            )


def verify_router(source: str) -> None:
    ast.parse(
        source
    )

    required = (
        ROUTER_HELPER_MARKER,
        ROUTER_SAVE_MARKER,
        ROUTER_CSVC_MARKER,
        "teaches_multigrade",
        "uses_multigrade_program_4yo",
        "uses_multigrade_program_5yo",
        "SchoolMn01CsvcInput",
    )

    for marker in required:
        if marker not in source:
            raise RuntimeError(
                "Router sau cài thiếu: "
                + marker
            )


def verify_model(source: str) -> None:
    ast.parse(
        source
    )

    for field in NEW_COLUMNS:
        if not re.search(
            rf"(?m)^\s*{re.escape(field)}(?:\s*:|\s*=)",
            source,
        ):
            raise RuntimeError(
                "Model sau cài thiếu: "
                + field
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
        "BÀI 13B-11.14.7.2 - "
        "MỞ RỘNG TRỰC TIẾP MN-01-GV: "
        "GV DẠY LỚP GHÉP + CT 4 TUỔI + CT 5 TUỔI"
    )
    print("=" * 132)
    print()
    print("CHỐT KIẾN TRÚC:")
    print(
        " - Chỉ sửa màn /doi-ngu/nhap-mn-01-gv hiện có."
    )
    print(
        " - KHÔNG tạo menu mới."
    )
    print(
        " - KHÔNG sửa giao diện/dữ liệu CSVC."
    )
    print(
        " - Số nhóm/lớp trong MN-01-GV chỉ ĐỌC từ CSVC."
    )
    print(
        " - Không cho nhập lại số lớp trong Đội ngũ."
    )
    print()
    print("BỔ SUNG CHO TỪNG GIÁO VIÊN:")
    print(
        " 1. Dạy lớp ghép: Chưa xác định / Có / Không."
    )
    print(
        " 2. Nếu Có -> Chương trình 4 tuổi: "
        "Chưa xác định / Có / Không."
    )
    print(
        " 3. Nếu Có -> Chương trình 5 tuổi: "
        "Chưa xác định / Có / Không."
    )
    print()
    print("TỰ TÍNH:")
    print(
        " - Tỷ lệ GV/lớp vẫn tự tính."
    )
    print(
        " - Mẫu số lớp lấy từ CSVC."
    )
    print()
    print("AN TOÀN:")
    print(
        " - Tự đảm bảo 3 field lớp ghép tồn tại."
    )
    print(
        " - Không tự điền dữ liệu cũ."
    )
    print(
        " - Backup model/router/template/database."
    )
    print(
        " - py_compile + Jinja + integrity + foreign key."
    )
    print(
        " - Có lỗi tự rollback toàn bộ."
    )
    print()

    for path in (
        DB,
        MODEL,
        ROUTER,
        TEMPLATE,
    ):
        if not path.exists():
            raise RuntimeError(
                f"Không tìm thấy: {path}"
            )

    before = snapshot_db()

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
        "staff_year_records:",
        before["staff_count"],
        "bản ghi",
    )
    print(
        "school_mn01_csvc_inputs:",
        before["csvc_count"],
        "bản ghi",
    )

    if (
        before["integrity"].lower()
        != "ok"
        or before["fk"] != 0
    ):
        raise RuntimeError(
            "Database không đạt kiểm tra an toàn trước cài."
        )

    router_before = read_text(
        ROUTER
    )
    template_before = read_text(
        TEMPLATE
    )
    model_before = read_text(
        MODEL
    )

    for marker in (
        "/doi-ngu/nhap-mn-01-gv",
        "gv_report_input_page",
        "gv_report_input_save",
        "SchoolMn01CsvcInput",
    ):
        if marker not in router_before:
            raise RuntimeError(
                "report_inputs.py thiếu nền MN-01-GV: "
                + marker
            )

    for marker in (
        "MN-01-GV – Đội ngũ giáo viên Mầm non",
        "2. Danh sách nhân sự của trường",
        "3. Rà soát chỉ tiêu MN-01-GV",
        "Tỉ lệ giáo viên/lớp",
    ):
        if marker not in template_before:
            raise RuntimeError(
                "gv_mn01.html không đúng nền hiện tại: "
                + marker
            )

    BACKUP.mkdir(
        parents=True,
        exist_ok=False,
    )

    backup_file(
        MODEL,
        MODEL_BACKUP,
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
        patched_model = patch_model(
            model_before
        )

        patched_router = patch_router(
            router_before
        )

        patched_template = patch_template(
            template_before
        )

        verify_model(
            patched_model
        )
        verify_router(
            patched_router
        )
        verify_template(
            patched_template
        )

        write_text(
            MODEL,
            patched_model,
        )
        write_text(
            ROUTER,
            patched_router,
        )
        write_text(
            TEMPLATE,
            patched_template,
        )

        compile_python(
            MODEL
        )
        compile_python(
            ROUTER
        )

        added_columns = ensure_db_columns()

        after = snapshot_db()

        missing_columns = [
            field
            for field in NEW_COLUMNS
            if field
            not in set(
                after["staff_columns"]
            )
        ]

        if missing_columns:
            raise RuntimeError(
                "Database sau cài thiếu field: "
                + ", ".join(
                    missing_columns
                )
            )

        if (
            after["staff_count"]
            != before["staff_count"]
        ):
            raise RuntimeError(
                "Số bản ghi staff_year_records "
                "bị thay đổi khi cài."
            )

        if (
            after["csvc_count"]
            != before["csvc_count"]
        ):
            raise RuntimeError(
                "Bài 14.7.2 không được thay đổi "
                "dữ liệu CSVC."
            )

        if (
            after["integrity"].lower()
            != "ok"
        ):
            raise RuntimeError(
                "integrity_check sau cài không OK."
            )

        if after["fk"] != 0:
            raise RuntimeError(
                "foreign_key_check sau cài "
                f"có {after['fk']} lỗi."
            )

        if added_columns:
            conn = db_connect()

            try:
                for column in added_columns:
                    nonnull = int(
                        conn.execute(
                            f'SELECT COUNT(*) '
                            f'FROM "{TABLE}" '
                            f'WHERE "{column}" IS NOT NULL'
                        ).fetchone()[0]
                    )

                    if nonnull != 0:
                        raise RuntimeError(
                            f"Field mới {column} "
                            "bị tự điền dữ liệu."
                        )
            finally:
                conn.close()

        clear_cache()

        print()
        print("KIỂM TRA SAU CÀI:")
        print(
            " - Route /doi-ngu/nhap-mn-01-gv: GIỮ NGUYÊN"
        )
        print(
            " - Menu: KHÔNG TẠO MỚI"
        )
        print(
            " - CSVC: KHÔNG SỬA"
        )
        print(
            " - Số nhóm/lớp tại MN-01-GV: CHỈ ĐỌC TỪ CSVC"
        )
        print(
            " - Ô nhập lớp trùng tại Đội ngũ: ĐÃ BỎ"
        )
        print(
            " - Dạy lớp ghép: ĐÃ BỔ SUNG"
        )
        print(
            " - Chương trình 4 tuổi: ĐÃ BỔ SUNG"
        )
        print(
            " - Chương trình 5 tuổi: ĐÃ BỔ SUNG"
        )
        print(
            " - CT 4 tuổi/5 tuổi chỉ hiện khi Dạy lớp ghép = Có"
        )
        print(
            " - staff_year_records:",
            after["staff_count"],
            "bản ghi - GIỮ NGUYÊN",
        )
        print(
            " - py_compile model/router: OK"
        )
        print(
            " - Jinja template: OK"
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
            "CÀI ĐẶT BÀI 13B-11.14.7.2 THÀNH CÔNG"
        )
        print("=" * 132)

        return 0

    except Exception:
        traceback.print_exc()

        print()
        print(
            "CÓ LỖI - ĐANG KHÔI PHỤC "
            "MODEL/ROUTER/TEMPLATE/DATABASE..."
        )

        for backup, target in (
            (
                MODEL_BACKUP,
                MODEL,
            ),
            (
                ROUTER_BACKUP,
                ROUTER,
            ),
            (
                TEMPLATE_BACKUP,
                TEMPLATE,
            ),
        ):
            try:
                shutil.copy2(
                    backup,
                    target,
                )
                print(
                    " - Đã khôi phục:",
                    target,
                )
            except Exception as exc:
                print(
                    " - Lỗi khôi phục",
                    target,
                    ":",
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
