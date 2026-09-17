from __future__ import annotations

import os
import re
import shutil
import sqlite3
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path

PROJECT = Path(os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")).resolve()
APP = PROJECT / "app"

MODEL = APP / "survey_models.py"
ROUTER = APP / "routers" / "surveys.py"
QUICK = APP / "templates" / "surveys" / "quick_entry.html"
EDIT = APP / "templates" / "surveys" / "person_edit.html"
YEAR = APP / "templates" / "surveys" / "year_records.html"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = PROJECT / "exports" / f"backup_gv_mobile_v1_9_dinh_danh_cccd_{STAMP}"

YEAR_ACTION_MARKER = "GV_MOBILE_V19_YEAR_ACTIONS"
CCCD_FIELD_MARKER = "GV_MOBILE_V19_CCCD_FIELD"
INTERNAL_ID_MARKER = "GV_MOBILE_V19_INTERNAL_ID"


def read_text(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(f"Không tìm thấy tệp bắt buộc: {path}")
    return path.read_text(encoding="utf-8-sig")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def backup_file(path: Path) -> None:
    rel = path.relative_to(PROJECT)
    dst = BACKUP / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dst)


def restore_file(path: Path) -> None:
    rel = path.relative_to(PROJECT)
    src = BACKUP / rel
    if src.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, path)


def import_database_path() -> Path:
    sys.path.insert(0, str(PROJECT))
    try:
        from app.database import DATABASE_PATH
        return Path(DATABASE_PATH)
    finally:
        try:
            sys.path.remove(str(PROJECT))
        except ValueError:
            pass


def backup_database(db_path: Path) -> None:
    if not db_path.exists():
        raise RuntimeError(f"Không tìm thấy database: {db_path}")
    dst = BACKUP / "database" / db_path.name
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(db_path, dst)


def restore_database(db_path: Path) -> None:
    src = BACKUP / "database" / db_path.name
    if src.exists():
        shutil.copy2(src, db_path)


def clear_cache() -> None:
    for cache in APP.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)


def get_function_block(text: str, func_name: str) -> tuple[int, int, str]:
    m = re.search(rf"^def\s+{re.escape(func_name)}\s*\(", text, re.MULTILINE)
    if not m:
        raise RuntimeError(f"Không tìm thấy hàm {func_name} trong surveys.py")

    start = m.start()
    next_match = re.search(
        r"^(?:@router\.[a-zA-Z_]+\(|def\s+[a-zA-Z_]\w*\s*\()",
        text[m.end():],
        re.MULTILINE,
    )
    end = m.end() + next_match.start() if next_match else len(text)
    return start, end, text[start:end]


def replace_function_block(text: str, func_name: str, new_block: str) -> str:
    start, end, _ = get_function_block(text, func_name)
    return text[:start] + new_block.rstrip() + "\n\n" + text[end:].lstrip("\n")


def ensure_once(block: str, old: str, new: str, label: str) -> str:
    if new in block:
        return block
    if old not in block:
        raise RuntimeError(f"Không tìm thấy điểm sửa: {label}")
    return block.replace(old, new, 1)


def patch_model(text: str) -> str:
    if re.search(r"^\s+citizen_id:\s*Mapped\[", text, re.MULTILINE):
        return text

    pattern = re.compile(
        r"(?P<block>\n    personal_id:\s*Mapped\[str\s*\|\s*None\]\s*=\s*mapped_column\(\n"
        r"        String\(50\),\n"
        r"        nullable=True,\n"
        r"        index=True,\n"
        r"    \)\n)",
        re.MULTILINE,
    )
    m = pattern.search(text)
    if not m:
        raise RuntimeError("Không tìm thấy khối personal_id trong survey_models.py")

    citizen = '''
    # Căn cước công dân chính thức nếu người dân cung cấp.
    # Trường này độc lập với personal_id và mã nội bộ SurveyPerson.code.
    citizen_id: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        index=True,
    )
'''
    return text[:m.end()] + citizen + text[m.end():]


def remove_missing_personal_id_completion_errors(text: str) -> str:
    old = '''        if missing_personal_id_count:
            errors.append(
                "Không thể hoàn thành phiếu: còn "
                f"{missing_personal_id_count} thành viên thiếu số định danh."
            )
'''
    return text.replace(old, "")


def patch_hien_thi_nhap_nhanh(block: str) -> str:
    if '"citizen_id": ""' not in block:
        block = ensure_once(
            block,
            '''            "personal_id": "",
            "residency_status": "THUONG_TRU",''',
            '''            "personal_id": "",
            "citizen_id": "",
            "residency_status": "THUONG_TRU",''',
            "person_form_data citizen_id",
        )

    old_warning = '''    if missing_personal_id_count:
        warnings.append(
            f"Còn {missing_personal_id_count} thành viên thiếu số định danh."
        )'''
    new_warning = '''    if missing_personal_id_count:
        warnings.append(
            f"{missing_personal_id_count} thành viên chưa có số định danh chính thức; "
            "hệ thống đang nhận diện bằng mã nội bộ."
        )'''
    if old_warning in block:
        block = block.replace(old_warning, new_warning, 1)

    old_blocker = '''    if missing_personal_id_count:
        completion_blockers.append(
            f"{missing_personal_id_count} thành viên chưa có số định danh."
        )
'''
    if old_blocker in block:
        block = block.replace(old_blocker, "", 1)

    return block


def add_citizen_param(block: str) -> str:
    if "citizen_id: Annotated[str, Form()]" in block:
        return block
    return ensure_once(
        block,
        '    personal_id: Annotated[str, Form()] = "",\n',
        '    personal_id: Annotated[str, Form()] = "",\n'
        '    citizen_id: Annotated[str, Form()] = "",\n',
        "tham số citizen_id",
    )


def add_citizen_normalize(block: str) -> str:
    if "citizen_id = chuan_hoa_ma(citizen_id)" in block:
        return block
    return ensure_once(
        block,
        "    personal_id = chuan_hoa_ma(personal_id)\n",
        "    personal_id = chuan_hoa_ma(personal_id)\n"
        "    citizen_id = chuan_hoa_ma(citizen_id)\n",
        "chuẩn hóa citizen_id",
    )


def add_citizen_form_data(block: str) -> str:
    if '"citizen_id": citizen_id' in block:
        return block
    return ensure_once(
        block,
        '        "personal_id": personal_id,\n',
        '        "personal_id": personal_id,\n'
        '        "citizen_id": citizen_id,\n',
        "form_data citizen_id",
    )


def add_citizen_validation(block: str, current_person: bool) -> str:
    if "Căn cước công dân dài quá 50 ký tự." not in block:
        block = ensure_once(
            block,
            '''    if len(personal_id) > 50:
        errors.append("Số định danh dài quá 50 ký tự.")
''',
            '''    if len(personal_id) > 50:
        errors.append("Số định danh dài quá 50 ký tự.")
    if len(citizen_id) > 50:
        errors.append("Căn cước công dân dài quá 50 ký tự.")
''',
            "kiểm tra độ dài CCCD",
        )

    if "duplicate_citizen_id" not in block:
        if current_person:
            duplicate = '''    if citizen_id:
        duplicate_citizen_id = db.scalar(
            select(SurveyPerson).where(
                SurveyPerson.citizen_id == citizen_id,
                SurveyPerson.id != person.id,
                SurveyPerson.is_active.is_(True),
            )
        )
        if duplicate_citizen_id is not None:
            errors.append("CCCD đã được dùng cho đối tượng khác.")

'''
        else:
            duplicate = '''    if citizen_id:
        duplicate_citizen_id = db.scalar(
            select(SurveyPerson).where(
                SurveyPerson.citizen_id == citizen_id,
                SurveyPerson.is_active.is_(True),
            )
        )
        if duplicate_citizen_id is not None:
            errors.append("CCCD đã được sử dụng cho đối tượng khác.")

'''
        anchor = "    duplicate_name ="
        if anchor not in block:
            raise RuntimeError("Không tìm thấy duplicate_name để chèn kiểm tra CCCD")
        block = block.replace(anchor, duplicate + anchor, 1)
    return block


def patch_quick_add(block: str) -> str:
    block = add_citizen_param(block)
    block = add_citizen_normalize(block)
    if '"citizen_id": citizen_id' not in block:
        block = ensure_once(
            block,
            '''        "personal_id": personal_id,
        "residency_status": residency_status,''',
            '''        "personal_id": personal_id,
        "citizen_id": citizen_id,
        "residency_status": residency_status,''',
            "quick person_form_data citizen_id",
        )
    block = add_citizen_validation(block, current_person=False)
    if "citizen_id=citizen_id or None" not in block:
        block = ensure_once(
            block,
            "        personal_id=personal_id or None,\n",
            "        personal_id=personal_id or None,\n"
            "        citizen_id=citizen_id or None,\n",
            "lưu CCCD thành viên nhanh",
        )
    return block


def patch_add_person(block: str) -> str:
    block = add_citizen_param(block)
    block = add_citizen_normalize(block)
    block = add_citizen_form_data(block)
    block = add_citizen_validation(block, current_person=False)
    if "citizen_id=citizen_id or None" not in block:
        block = ensure_once(
            block,
            "        personal_id=personal_id or None,\n",
            "        personal_id=personal_id or None,\n"
            "        citizen_id=citizen_id or None,\n",
            "lưu CCCD đối tượng",
        )
    return block


def patch_edit_form_helper(block: str) -> str:
    if '"citizen_id": person.citizen_id or ""' not in block:
        block = ensure_once(
            block,
            '''            "personal_id": person.personal_id or "",
            "ministry_student_code": (''',
            '''            "personal_id": person.personal_id or "",
            "citizen_id": person.citizen_id or "",
            "ministry_student_code": (''',
            "form sửa citizen_id",
        )
    return block


def patch_update_person(block: str) -> str:
    block = add_citizen_param(block)
    block = add_citizen_normalize(block)
    block = add_citizen_form_data(block)
    block = add_citizen_validation(block, current_person=True)
    if "person.citizen_id = citizen_id or None" not in block:
        block = ensure_once(
            block,
            "    person.personal_id = personal_id or None\n",
            "    person.personal_id = personal_id or None\n"
            "    person.citizen_id = citizen_id or None\n",
            "cập nhật CCCD",
        )
    return block


def patch_year_get(block: str) -> str:
    if "next_person_url =" not in block:
        anchor = '''    history_rows = tao_du_lieu_lich_su_nam_hoc(
        db=db,
        person_id=person_id,
        survey_form_id=survey_form.id,
    )
'''
        if anchor not in block:
            raise RuntimeError("Không tìm thấy history_rows trong theo_doi_nam_hoc_doi_tuong")
        addition = '''
    # Điều hướng nhanh cho giáo viên trên điện thoại sau khi lưu.
    active_people = db.scalars(
        select(SurveyPerson)
        .where(
            SurveyPerson.household_id == household_id,
            SurveyPerson.is_active.is_(True),
        )
        .order_by(
            SurveyPerson.date_of_birth.asc(),
            SurveyPerson.full_name.asc(),
            SurveyPerson.id.asc(),
        )
    ).all()

    current_person_index = next(
        (
            index
            for index, item in enumerate(active_people)
            if int(item.id) == int(person_id)
        ),
        -1,
    )
    next_person = (
        active_people[current_person_index + 1]
        if 0 <= current_person_index < len(active_people) - 1
        else None
    )
    next_person_url = (
        f"/dieu-tra/{batch_id}/ho-dan/{household_id}/doi-tuong/"
        f"{next_person.id}/nam-hoc?school_year_id={school_year_id}#year_record_form"
        if next_person is not None
        else None
    )
    quick_entry_url = (
        f"/dieu-tra/{batch_id}/ho-dan/{household_id}/nhap-nhanh#members"
    )
    work_url = "/"
'''
        block = block.replace(anchor, anchor + addition, 1)

    if '"year_record_saved": status == "year_record_saved"' not in block:
        block = ensure_once(
            block,
            '''            "thong_bao": STATUS_MESSAGES.get(status),
            "thong_bao_loi": None,''',
            '''            "thong_bao": STATUS_MESSAGES.get(status),
            "thong_bao_loi": None,
            "year_record_saved": status == "year_record_saved",
            "next_person_url": next_person_url,
            "quick_entry_url": quick_entry_url,
            "work_url": work_url,''',
            "context điều hướng sau lưu năm học",
        )
    return block


def patch_year_post(block: str) -> str:
    if '"year_record_saved": False' not in block:
        block = ensure_once(
            block,
            '''                "thong_bao": None,
                "thong_bao_loi": " ".join(errors),''',
            '''                "thong_bao": None,
                "thong_bao_loi": " ".join(errors),
                "year_record_saved": False,
                "next_person_url": None,
                "quick_entry_url": (
                    f"/dieu-tra/{batch_id}/ho-dan/{household_id}/nhap-nhanh#members"
                ),
                "work_url": "/",''',
            "context lỗi năm học",
        )
    return block


def patch_router(text: str) -> str:
    text = remove_missing_personal_id_completion_errors(text)

    transforms = [
        ("hien_thi_trang_nhap_nhanh", patch_hien_thi_nhap_nhanh),
        ("them_doi_tuong_tu_nhap_nhanh", patch_quick_add),
        ("them_doi_tuong", patch_add_person),
        ("hien_thi_form_sua_doi_tuong", patch_edit_form_helper),
        ("cap_nhat_doi_tuong", patch_update_person),
        ("theo_doi_nam_hoc_doi_tuong", patch_year_get),
        ("luu_theo_doi_nam_hoc", patch_year_post),
    ]
    for func_name, transformer in transforms:
        _, _, block = get_function_block(text, func_name)
        text = replace_function_block(text, func_name, transformer(block))

    if "SurveyPerson.citizen_id.ilike(search_value)" not in text:
        anchor = "                            SurveyPerson.personal_id.ilike(search_value),\n"
        if anchor in text:
            text = text.replace(
                anchor,
                anchor + "                            SurveyPerson.citizen_id.ilike(search_value),\n",
                1,
            )
    return text


def find_matching_div_end(text: str, start: int) -> int:
    tag_re = re.compile(r"<div\b[^>]*>|</div>", re.IGNORECASE)
    depth = 0
    for m in tag_re.finditer(text, start):
        tag = m.group(0).lower()
        if tag.startswith("<div") and not tag.startswith("</"):
            depth += 1
        else:
            depth -= 1
            if depth == 0:
                return m.end()
    raise RuntimeError("Không tìm được điểm kết thúc DIV chứa trường biểu mẫu.")


def find_parent_div(text: str, position: int) -> tuple[int, int, str]:
    start = text.rfind("<div", 0, position)
    while start >= 0:
        try:
            end = find_matching_div_end(text, start)
        except RuntimeError:
            start = text.rfind("<div", 0, start)
            continue
        if end > position:
            open_end = text.find(">", start) + 1
            return start, end, text[start:open_end]
        start = text.rfind("<div", 0, start)
    raise RuntimeError("Không tìm được DIV cha của trường personal_id.")


def insert_field_after_input(
    text: str,
    *,
    input_name: str,
    value_expr: str,
    include_internal_id: bool,
) -> str:
    if CCCD_FIELD_MARKER in text:
        return text

    m = re.search(
        rf'<input\b[^>]*\bname=["\']{re.escape(input_name)}["\'][^>]*>',
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if not m:
        raise RuntimeError(f"Không tìm thấy input name={input_name}")

    _, end, open_tag = find_parent_div(text, m.start())

    internal = ""
    if include_internal_id:
        internal = f'''
{open_tag}
    <!-- === {INTERNAL_ID_MARKER} === -->
    <label>Mã định danh nội bộ</label>
    <input type="text" value="{{{{ person.code }}}}" readonly>
    <small>Mã do hệ thống tự sinh; không phải số định danh cá nhân hay CCCD.</small>
</div>
'''

    citizen = f'''
{open_tag}
    <!-- === {CCCD_FIELD_MARKER} === -->
    <label for="citizen_id">Căn cước công dân</label>
    <input
        id="citizen_id"
        type="text"
        name="citizen_id"
        value="{value_expr}"
        maxlength="50"
        inputmode="numeric"
        autocomplete="off"
        placeholder="Nhập CCCD nếu có"
    >
    <small>Không bắt buộc. Nếu chưa có, hệ thống vẫn dùng mã định danh nội bộ.</small>
</div>
'''
    return text[:end] + internal + citizen + text[end:]


def patch_quick_template(text: str) -> str:
    if CCCD_FIELD_MARKER not in text:
        text = insert_field_after_input(
            text,
            input_name="personal_id",
            value_expr="{{ person_form_data.citizen_id or '' }}",
            include_internal_id=False,
        )
    return text


def patch_edit_template(text: str) -> str:
    if CCCD_FIELD_MARKER not in text:
        text = insert_field_after_input(
            text,
            input_name="personal_id",
            value_expr="{{ form_data.citizen_id or '' }}",
            include_internal_id=True,
        )
    return text


YEAR_CSS = f'''
    /* === {YEAR_ACTION_MARKER}_CSS_START === */
    .pc-v19-after-save {{
        margin: 16px 0 18px;
        padding: 14px;
        border: 1px solid #b9dfc3;
        border-radius: 14px;
        background: #f1fbf4;
    }}
    .pc-v19-after-save__title {{
        margin: 0 0 10px;
        font-weight: 800;
        color: #176b33;
    }}
    .pc-v19-after-save__actions {{
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 10px;
    }}
    .pc-v19-after-save__actions a {{
        display: flex;
        align-items: center;
        justify-content: center;
        min-height: 48px;
        padding: 10px 12px;
        border-radius: 12px;
        font-weight: 800;
        text-align: center;
        text-decoration: none;
        border: 1px solid #c8d8e8;
        background: #fff;
        color: #0b5cab;
    }}
    .pc-v19-after-save__actions a.pc-v19-next {{
        background: #0b72d9;
        color: #fff;
        border-color: #0b72d9;
    }}
    @media (max-width: 700px) {{
        .pc-v19-after-save {{
            margin: 10px 0 14px;
            padding: 12px;
        }}
        .pc-v19-after-save__actions {{
            grid-template-columns: 1fr;
        }}
        .pc-v19-after-save__actions a {{
            min-height: 52px;
            font-size: 17px;
        }}
    }}
    /* === {YEAR_ACTION_MARKER}_CSS_END === */
'''

YEAR_ACTIONS = f'''
    {{% if nguoi_dung.role_code == 'GIAO_VIEN' and year_record_saved %}}
    <!-- === {YEAR_ACTION_MARKER}_START === -->
    <section class="pc-v19-after-save">
        <p class="pc-v19-after-save__title">✓ Đã lưu thông tin năm học của {{{{ person.full_name }}}}</p>
        <div class="pc-v19-after-save__actions">
            {{% if next_person_url %}}
            <a class="pc-v19-next" href="{{{{ next_person_url }}}}">
                Thành viên tiếp theo →
            </a>
            {{% else %}}
            <a class="pc-v19-next" href="{{{{ quick_entry_url }}}}">
                Đã hết thành viên – về phiếu
            </a>
            {{% endif %}}
            <a href="{{{{ work_url }}}}">
                ← Quay về trang làm việc
            </a>
        </div>
    </section>
    <!-- === {YEAR_ACTION_MARKER}_END === -->
    {{% endif %}}
'''


def patch_year_template(text: str) -> str:
    if f"{YEAR_ACTION_MARKER}_CSS_START" not in text:
        if "</style>" in text:
            text = text.replace("</style>", YEAR_CSS + "\n</style>", 1)
        elif "</head>" in text:
            text = text.replace(
                "</head>",
                "<style>\n" + YEAR_CSS + "\n</style>\n</head>",
                1,
            )
        else:
            raise RuntimeError("Không tìm thấy điểm chèn CSS trong year_records.html")

    if f"{YEAR_ACTION_MARKER}_START" not in text:
        form_id = text.find('id="year_record_form"')
        if form_id < 0:
            raise RuntimeError('Không tìm thấy id="year_record_form" trong year_records.html')
        form_start = text.rfind("<form", 0, form_id)
        if form_start < 0:
            raise RuntimeError("Không tìm thấy thẻ form của year_record_form")
        text = text[:form_start] + YEAR_ACTIONS + "\n" + text[form_start:]
    return text


def migrate_database(db_path: Path) -> None:
    con = sqlite3.connect(str(db_path))
    try:
        columns = {
            row[1]
            for row in con.execute("PRAGMA table_info(survey_people)").fetchall()
        }
        if "citizen_id" not in columns:
            con.execute("ALTER TABLE survey_people ADD COLUMN citizen_id VARCHAR(50)")
        con.execute(
            "CREATE INDEX IF NOT EXISTS ix_survey_people_citizen_id ON survey_people(citizen_id)"
        )
        con.execute(
            "UPDATE survey_people SET code = 'DT-' || printf('%08d', id) "
            "WHERE code IS NULL OR trim(code) = ''"
        )
        con.commit()
    finally:
        con.close()


def verify_database(db_path: Path) -> None:
    con = sqlite3.connect(str(db_path))
    try:
        columns = {
            row[1]
            for row in con.execute("PRAGMA table_info(survey_people)").fetchall()
        }
        if "citizen_id" not in columns:
            raise RuntimeError("Database chưa có cột citizen_id.")
        missing_code = con.execute(
            "SELECT COUNT(*) FROM survey_people WHERE code IS NULL OR trim(code)=''"
        ).fetchone()[0]
        if missing_code:
            raise RuntimeError(f"Còn {missing_code} đối tượng thiếu mã nội bộ.")
    finally:
        con.close()


def verify_files() -> None:
    model = read_text(MODEL)
    router = read_text(ROUTER)
    quick = read_text(QUICK)
    edit = read_text(EDIT)
    year = read_text(YEAR)

    required = [
        ("model citizen_id", "citizen_id: Mapped[str | None]", model),
        ("router citizen param", "citizen_id: Annotated[str, Form()]", router),
        ("router update citizen", "person.citizen_id = citizen_id or None", router),
        ("quick CCCD", CCCD_FIELD_MARKER, quick),
        ("edit CCCD", CCCD_FIELD_MARKER, edit),
        ("year actions", f"{YEAR_ACTION_MARKER}_START", year),
        ("next person context", '"next_person_url": next_person_url', router),
        ("year saved context", '"year_record_saved": status == "year_record_saved"', router),
    ]
    for label, marker, source in required:
        if marker not in source:
            raise RuntimeError(f"Kiểm tra không đạt: {label}")

    if 'f"{missing_personal_id_count} thành viên thiếu số định danh."' in router:
        raise RuntimeError(
            "Vẫn còn lỗi chặn hoàn thành do thiếu số định danh trong surveys.py"
        )

    subprocess.run(
        [sys.executable, "-m", "py_compile", str(MODEL), str(ROUTER)],
        cwd=PROJECT,
        check=True,
    )

    from jinja2 import Environment, FileSystemLoader
    env = Environment(loader=FileSystemLoader(str(APP / "templates")))
    for name in (
        "surveys/quick_entry.html",
        "surveys/person_edit.html",
        "surveys/year_records.html",
    ):
        env.get_template(name)


def main() -> int:
    print("=" * 104)
    print("GIAO VIEN MOBILE V1.9 - DINH DANH NOI BO + CCCD + CHUYEN THANH VIEN")
    print("=" * 104)
    print("")
    print("NỘI DUNG:")
    print(" 1. Số định danh cá nhân là dữ liệu chính thức, có thể để trống.")
    print(" 2. Mã nội bộ dùng SurveyPerson.code dạng DT-xxxxxxxx, tự sinh sẵn.")
    print(" 3. Thêm ô Căn cước công dân riêng.")
    print(" 4. Thiếu Số định danh/CCCD KHÔNG chặn Hoàn thành phiếu.")
    print(" 5. Sau Lưu thông tin năm học có Thành viên tiếp theo / Quay về trang làm việc.")
    print("")
    print("KHÔNG THAY ĐỔI:")
    print(" - Luồng Phiếu phân công -> Nhập nhanh.")
    print(" - Dữ liệu đã nhập.")
    print(" - Báo cáo, Đội ngũ, CSVC.")
    print(" - Quyền Sở/Xã/Trường.")
    print("")

    for path in (MODEL, ROUTER, QUICK, EDIT, YEAR):
        if not path.exists():
            raise RuntimeError(f"Không tìm thấy: {path}")

    db_path = import_database_path()

    BACKUP.mkdir(parents=True, exist_ok=False)
    for path in (MODEL, ROUTER, QUICK, EDIT, YEAR):
        backup_file(path)
    backup_database(db_path)

    try:
        write_text(MODEL, patch_model(read_text(MODEL)))
        write_text(ROUTER, patch_router(read_text(ROUTER)))
        write_text(QUICK, patch_quick_template(read_text(QUICK)))
        write_text(EDIT, patch_edit_template(read_text(EDIT)))
        write_text(YEAR, patch_year_template(read_text(YEAR)))

        migrate_database(db_path)
        verify_database(db_path)
        verify_files()
        clear_cache()

        print("")
        print("CAI DAT GIAO VIEN MOBILE V1.9 THANH CONG")
        print("Backup:", BACKUP)
        print("Database:", db_path)
        print("")
        print("KIỂM TRA:")
        print(" - Nhập nhanh: có ô CCCD.")
        print(" - Sửa thành viên: có Mã nội bộ + CCCD.")
        print(" - Thiếu Số định danh/CCCD vẫn hoàn thành được nếu dữ liệu khác đủ.")
        print(" - Lưu năm học: có Thành viên tiếp theo / Quay về trang làm việc.")
        return 0

    except Exception:
        traceback.print_exc()
        print("")
        print("CÓ LỖI - ĐANG KHÔI PHỤC...")
        for path in (MODEL, ROUTER, QUICK, EDIT, YEAR):
            restore_file(path)
        restore_database(db_path)
        clear_cache()
        print("ĐÃ KHÔI PHỤC SOURCE VÀ DATABASE VỀ TRƯỚC V1.9.")
        print("Backup:", BACKUP)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
