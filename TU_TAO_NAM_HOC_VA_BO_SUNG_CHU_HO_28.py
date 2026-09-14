# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
import hashlib
import py_compile
import re
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(r"C:\PhoCap")
APP = ROOT / "app"
DB = ROOT / "data" / "phocap.db"
SURVEYS = APP / "routers" / "surveys.py"
QUICK = APP / "templates" / "surveys" / "quick_entry.html"
BACKUPS = ROOT / "backups"
EXPORTS = ROOT / "exports"
OUT = EXPORTS / "TU_TAO_NAM_HOC_VA_BO_SUNG_CHU_HO_28.txt"

MARK_HELPER = "FIX28_HEAD_PERSON_PROMPT"
MARK_QUICK_ADD = "FIX28_CREATE_YEAR_RECORD_FOR_NEW_PERSON"
MARK_FIX26G = "FIX28_AUTOCREATE_YEAR_RECORD_IN_FIX26G"
MARK_UI = "FIX28_HEAD_PERSON_PROMPT_UI"


def log(f, *parts):
    line = " ".join(str(x) for x in parts)
    print(line)
    f.write(line + "\n")
    f.flush()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as src:
        for block in iter(lambda: src.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def db_precheck():
    con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True, timeout=30)
    try:
        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
        fk = con.execute("PRAGMA foreign_key_check").fetchall()

        def columns(table):
            return {str(r[1]) for r in con.execute(f'PRAGMA table_info("{table}")').fetchall()}

        person_cols = columns("survey_people")
        year_cols = columns("survey_person_year_records")
        counts = con.execute(
            '''
            SELECT
                (SELECT COUNT(*) FROM survey_people),
                (SELECT COUNT(*) FROM survey_person_year_records),
                (
                    SELECT COUNT(*)
                    FROM survey_people p
                    WHERE p.is_active = 1
                      AND NOT EXISTS (
                          SELECT 1
                          FROM survey_person_year_records y
                          WHERE y.survey_person_id = p.id
                            AND y.school_year_id = 2
                      )
                )
            '''
        ).fetchone()
    finally:
        con.close()

    if integrity != "ok" or fk:
        raise RuntimeError(f"DB health không đạt: integrity={integrity}; FK={len(fk)}")

    required_person = {
        "id", "household_id", "full_name", "date_of_birth",
        "relationship_to_head", "is_active",
    }
    required_year = {
        "id", "survey_form_id", "survey_person_id", "school_year_id", "learning_status",
    }
    mp = sorted(required_person - person_cols)
    my = sorted(required_year - year_cols)
    if mp or my:
        raise RuntimeError(
            f"Schema chưa đúng nền. survey_people thiếu={mp}; "
            f"survey_person_year_records thiếu={my}"
        )
    return integrity, len(fk), counts


def function_span(text: str, name: str) -> tuple[int, int]:
    tree = ast.parse(text)
    lines = text.splitlines(keepends=True)
    offsets = [0]
    total = 0
    for line in lines:
        total += len(line)
        offsets.append(total)
    nodes = [
        n for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name
    ]
    if len(nodes) != 1:
        raise RuntimeError(f"Cần đúng 1 hàm {name}; thực tế={len(nodes)}.")
    node = nodes[0]
    if node.end_lineno is None:
        raise RuntimeError(f"Không xác định được cuối hàm {name}.")
    return offsets[node.lineno - 1], offsets[node.end_lineno]


def get_function(text: str, name: str) -> str:
    a, b = function_span(text, name)
    return text[a:b]


def replace_function(text: str, name: str, fn: str) -> str:
    a, b = function_span(text, name)
    return text[:a] + fn.rstrip() + "\n\n" + text[b:]


def patch_quick_helper(source: str):
    fn = get_function(source, "hien_thi_trang_nhap_nhanh")
    if MARK_HELPER in fn:
        return source, "ALREADY_PRESENT"

    anchor = '    record_map = completion_data["record_map"]\n'
    if anchor not in fn:
        raise RuntimeError("Không tìm thấy record_map trong helper Nhập nhanh.")

    block = f'''    # === {MARK_HELPER}_START ===
    _fix28_active_head_person = next(
        (
            item
            for item in people
            if item.is_active
            and la_quan_he_chu_ho(item.relationship_to_head)
        ),
        None,
    )
    household_head_needs_person = bool(
        chuan_hoa_van_ban(household.head_name or "")
        and _fix28_active_head_person is None
    )
    # === {MARK_HELPER}_END ===

'''
    fn = fn.replace(anchor, block + anchor, 1)

    old = '            "full_name": "",\n'
    if old not in fn:
        raise RuntimeError("Không tìm thấy full_name mặc định.")
    fn = fn.replace(
        old,
        '''            "full_name": (
                household.head_name if household_head_needs_person else ""
            ),
''',
        1,
    )

    old = '            "relationship_to_head": "Con",\n'
    if old not in fn:
        raise RuntimeError("Không tìm thấy relationship_to_head mặc định.")
    fn = fn.replace(
        old,
        '''            "relationship_to_head": (
                "Chủ hộ" if household_head_needs_person else "Con"
            ),
''',
        1,
    )

    old = '            "household": household,\n'
    if old not in fn:
        raise RuntimeError("Không tìm thấy household trong context.")
    fn = fn.replace(
        old,
        old + '            "household_head_needs_person": household_head_needs_person,\n',
        1,
    )
    return replace_function(source, "hien_thi_trang_nhap_nhanh", fn), "PATCHED"


def patch_quick_add_person(source: str):
    fn = get_function(source, "them_doi_tuong_tu_nhap_nhanh")
    if MARK_QUICK_ADD in fn:
        return source, "ALREADY_PRESENT"

    anchor = '    person.code = f"DT-{person.id:08d}"\n\n'
    if anchor not in fn:
        raise RuntimeError("Không tìm thấy điểm sau db.flush() của thành viên mới.")

    block = anchor + f'''    # === {MARK_QUICK_ADD}_START ===
    _fix28_year_id = int(survey_form.survey_batch.school_year_id)
    _fix28_year_record = db.scalar(
        select(SurveyPersonYearRecord).where(
            SurveyPersonYearRecord.survey_form_id == survey_form.id,
            SurveyPersonYearRecord.survey_person_id == person.id,
            SurveyPersonYearRecord.school_year_id == _fix28_year_id,
        )
    )
    if _fix28_year_record is None:
        _fix28_year_record = SurveyPersonYearRecord(
            survey_form_id=survey_form.id,
            survey_person_id=person.id,
            school_year_id=_fix28_year_id,
            learning_status="CHUA_XAC_DINH",
        )
        db.add(_fix28_year_record)
    # === {MARK_QUICK_ADD}_END ===

'''
    fn = fn.replace(anchor, block, 1)
    return replace_function(source, "them_doi_tuong_tu_nhap_nhanh", fn), "PATCHED"


def patch_fix26g(source: str):
    fn = get_function(source, "fix26g_luu_chi_bao_nhanh")
    if MARK_FIX26G in fn:
        return source, "ALREADY_PRESENT"

    expected_message = (
        "Chưa có bản ghi năm học. Hãy bấm Lưu thông tin năm học "
        "một lần trước khi lưu riêng chỉ báo."
    )
    if expected_message not in fn:
        raise RuntimeError("FIX26G không còn block báo thiếu bản ghi năm học dự kiến.")

    pattern = re.compile(
        r'(?P<i>^[ \t]*)if record is None:\n'
        r'(?P<body>(?:(?!^[ \t]*allowed_locations\s*=).)*?)'
        r'(?=^[ \t]*allowed_locations\s*=)',
        flags=re.M | re.S,
    )
    m = pattern.search(fn)
    if m is None:
        raise RuntimeError("Không xác định được if record is None của FIX26G.")

    i = m.group("i")
    replacement = f'''{i}if record is None:
{i}    # === {MARK_FIX26G}_START ===
{i}    record = SurveyPersonYearRecord(
{i}        survey_form_id=survey_form.id,
{i}        survey_person_id=person.id,
{i}        school_year_id=school_year_id,
{i}        learning_status="CHUA_XAC_DINH",
{i}    )
{i}    db.add(record)
{i}    try:
{i}        db.flush()
{i}    except Exception:
{i}        db.rollback()
{i}        return {{
{i}            "ok": False,
{i}            "message": (
{i}                "Không thể tạo hồ sơ năm học cho đối tượng. "
{i}                "Dữ liệu cũ được giữ nguyên."
{i}            ),
{i}        }}
{i}    # === {MARK_FIX26G}_END ===

'''
    fn = fn[:m.start()] + replacement + fn[m.end():]
    return replace_function(source, "fix26g_luu_chi_bao_nhanh", fn), "PATCHED"


def patch_quick_template(text: str):
    if MARK_UI in text:
        return text, "ALREADY_PRESENT"

    details_anchor = (
        '<details class="pc-gv-v18-section" '
        '{% if thong_bao_loi and person_form_data.full_name %}'
        'open{% endif %}>'
    )
    if details_anchor not in text:
        raise RuntimeError("Không tìm thấy details Thêm thành viên đúng nền Mobile.")

    block = f'''{{# === {MARK_UI}_START === #}}
            {{% if household_head_needs_person %}}
            <div class="pc-gv-v18-alert" style="margin-bottom:12px;">
                <strong>👤 Chủ hộ chưa có trong danh sách đối tượng điều tra.</strong><br>
                Hệ thống đã điền sẵn tên <strong>{{{{ household.head_name }}}}</strong>
                và quan hệ <strong>Chủ hộ</strong> ở biểu mẫu bên dưới.
                Hãy bổ sung Ngày sinh, Giới tính, Dân tộc và Số định danh nếu có.
                Nếu chủ hộ thuộc phạm vi 0–60 tuổi thì cần bổ sung để điều tra;
                nếu trên 60 tuổi có thể bỏ qua khi không thuộc phạm vi nghiệp vụ cần theo dõi.
            </div>
            {{% endif %}}
            {{# === {MARK_UI}_END === #}}

'''
    text = text.replace(
        details_anchor,
        block
        + '<details class="pc-gv-v18-section" '
          '{% if household_head_needs_person or '
          '(thong_bao_loi and person_form_data.full_name) %}'
          'open{% endif %}>',
        1,
    )

    summary_anchor = '<summary>＋ Thêm thành viên mới</summary>'
    if summary_anchor not in text:
        raise RuntimeError("Không tìm thấy summary Thêm thành viên mới.")
    text = text.replace(
        summary_anchor,
        '''<summary>
                    {% if household_head_needs_person %}
                        👤 Bổ sung chủ hộ vào đối tượng điều tra
                    {% else %}
                        ＋ Thêm thành viên mới
                    {% endif %}
                </summary>''',
        1,
    )
    return text, "PATCHED"


def verify_source(source: str):
    ast.parse(source)
    required = (
        MARK_HELPER,
        MARK_QUICK_ADD,
        MARK_FIX26G,
        '"household_head_needs_person": household_head_needs_person',
        'learning_status="CHUA_XAC_DINH"',
        'def fix26g_luu_chi_bao_nhanh(',
        'def them_doi_tuong_tu_nhap_nhanh(',
    )
    missing = [x for x in required if x not in source]
    if missing:
        raise RuntimeError("surveys.py sau sửa thiếu: " + repr(missing))


def verify_template(text: str):
    required = (
        MARK_UI,
        "Chủ hộ chưa có trong danh sách đối tượng điều tra",
        "Bổ sung chủ hộ vào đối tượng điều tra",
        "household_head_needs_person",
    )
    missing = [x for x in required if x not in text]
    if missing:
        raise RuntimeError("quick_entry.html sau sửa thiếu: " + repr(missing))

    from jinja2 import Environment
    Environment().parse(text)


def clear_cache():
    for cache in APP.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)


def main():
    EXPORTS.mkdir(parents=True, exist_ok=True)
    BACKUPS.mkdir(parents=True, exist_ok=True)

    with OUT.open("w", encoding="utf-8-sig", newline="\n") as f:
        log(f, "=" * 165)
        log(f, "FIX 28 - TỰ TẠO HỒ SƠ NĂM HỌC + NHẮC BỔ SUNG CHỦ HỘ")
        log(f, "SOURCE ONLY - KHÔNG GHI DATABASE TRONG LÚC CÀI")
        log(f, "=" * 165)

        for p in (DB, SURVEYS, QUICK):
            if not p.exists():
                raise RuntimeError(f"Không tìm thấy: {p}")

        integrity, fk_count, counts = db_precheck()
        db_sha_before = sha256_file(DB)

        log(f, "DB_SHA_BEFORE =", db_sha_before)
        log(f, "INTEGRITY =", integrity)
        log(f, "FK_COUNT =", fk_count)
        log(
            f,
            "CURRENT_COUNTS =",
            {
                "survey_people": int(counts[0] or 0),
                "year_records": int(counts[1] or 0),
                "active_people_missing_year2": int(counts[2] or 0),
            },
        )

        source_before = SURVEYS.read_text(encoding="utf-8-sig")
        quick_before = QUICK.read_text(encoding="utf-8-sig")

        for fn_name in (
            "hien_thi_trang_nhap_nhanh",
            "them_doi_tuong_tu_nhap_nhanh",
            "fix26g_luu_chi_bao_nhanh",
        ):
            get_function(source_before, fn_name)

        required_quick = (
            "GV_MOBILE_V18_QUICK_START",
            "＋ Thêm thành viên mới",
            'action="/dieu-tra/{{ batch.id }}/ho-dan/{{ household.id }}/nhap-nhanh/them-doi-tuong"',
        )
        missing_quick = [x for x in required_quick if x not in quick_before]
        if missing_quick:
            raise RuntimeError(
                "quick_entry.html không đúng nền Mobile hiện tại: " + repr(missing_quick)
            )

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_root = BACKUPS / f"source_truoc_FIX28_{stamp}"
        survey_backup = backup_root / SURVEYS.relative_to(ROOT)
        quick_backup = backup_root / QUICK.relative_to(ROOT)
        survey_backup.parent.mkdir(parents=True, exist_ok=False)
        quick_backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(SURVEYS, survey_backup)
        shutil.copy2(QUICK, quick_backup)
        log(f, "SOURCE_BACKUP =", backup_root)

        try:
            source, s1 = patch_quick_helper(source_before)
            source, s2 = patch_quick_add_person(source)
            source, s3 = patch_fix26g(source)
            quick, q1 = patch_quick_template(quick_before)

            SURVEYS.write_text(source, encoding="utf-8")
            QUICK.write_text(quick, encoding="utf-8")

            py_compile.compile(str(SURVEYS), doraise=True)
            verify_source(SURVEYS.read_text(encoding="utf-8"))
            verify_template(QUICK.read_text(encoding="utf-8"))
            clear_cache()

            log(f, "PATCH_QUICK_HELPER =", s1)
            log(f, "PATCH_NEW_PERSON_YEAR_RECORD =", s2)
            log(f, "PATCH_FIX26G_AUTOCREATE =", s3)
            log(f, "PATCH_QUICK_UI =", q1)
            log(f, "PY_COMPILE = PASS")
            log(f, "JINJA_VERIFY = PASS")

        except Exception:
            shutil.copy2(survey_backup, SURVEYS)
            shutil.copy2(quick_backup, QUICK)
            clear_cache()
            log(f, "ROLLBACK_SOURCE = PASS")
            raise

        db_sha_after = sha256_file(DB)
        if db_sha_after != db_sha_before:
            shutil.copy2(survey_backup, SURVEYS)
            shutil.copy2(quick_backup, QUICK)
            clear_cache()
            raise RuntimeError("DB thay đổi trong lúc cài source; source đã rollback.")

        log(f, "DB_SHA_AFTER =", db_sha_after)
        log(f, "DATABASE_WRITES_THIS_RUN = 0")
        log(f, "FIX28_SUCCESS = YES")
        log(f, "")
        log(f, "NGUYÊN TẮC SAU FIX28:")
        log(f, " - Thành viên mới tại Nhập nhanh có luôn hồ sơ năm học hiện hành.")
        log(f, " - Đối tượng cũ thiếu year-record: FIX26G tự tạo ở lần cập nhật chỉ báo đầu tiên.")
        log(f, " - Chủ hộ chưa có SurveyPerson: Nhập nhanh mở sẵn biểu mẫu bổ sung chủ hộ.")
        log(f, " - Tên/quan hệ Chủ hộ điền sẵn; GV nhập ngày sinh, giới tính, dân tộc, định danh nếu có.")
        log(f, " - Không tự đoán nhân thân và không sao chép mù dữ liệu năm trước.")
        log(f, "=" * 165)

    return 0


if __name__ == "__main__":
    try:
        rc = main()
    except Exception as exc:
        try:
            EXPORTS.mkdir(parents=True, exist_ok=True)
            with OUT.open("a", encoding="utf-8-sig", newline="\n") as f:
                log(f, "")
                log(f, "=" * 165)
                log(f, "FIX28_SUCCESS = NO")
                log(f, "ERROR =", repr(exc))
                if DB.exists():
                    log(f, "DB_SHA_CURRENT =", sha256_file(DB))
                log(f, "DỪNG AN TOÀN.")
                log(f, "=" * 165)
        except Exception:
            print("ERROR =", repr(exc))
        rc = 1

    raise SystemExit(rc)
