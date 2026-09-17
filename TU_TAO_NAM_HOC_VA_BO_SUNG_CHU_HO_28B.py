# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
import hashlib
import py_compile
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
OUT = EXPORTS / "TU_TAO_NAM_HOC_VA_BO_SUNG_CHU_HO_28B.txt"

EXPECTED_DB_SHA = "79a74596643185bf7f0b4de1d3e2924d5ed91621171b3c680cded500c02a281f"

MARK_HELPER = "FIX28B_HEAD_PERSON_PROMPT"
MARK_QUICK_ADD = "FIX28B_CREATE_YEAR_RECORD_FOR_NEW_PERSON"
MARK_FIX26G = "FIX28B_AUTOCREATE_YEAR_RECORD_IN_FIX26G"
MARK_UI = "FIX28B_HEAD_PERSON_PROMPT_UI"
UI_DETAILS_ID = "fix28b-head-person-details"


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
        wal = Path(str(DB) + "-wal")
        journal = Path(str(DB) + "-journal")
        wal_size = wal.stat().st_size if wal.exists() else 0
        journal_size = journal.stat().st_size if journal.exists() else 0
        counts = con.execute(
            """
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
            """
        ).fetchone()
        person_cols = {r[1] for r in con.execute('PRAGMA table_info("survey_people")')}
        year_cols = {r[1] for r in con.execute('PRAGMA table_info("survey_person_year_records")')}
    finally:
        con.close()

    if integrity != "ok" or fk:
        raise RuntimeError(f"DB health không đạt: integrity={integrity}; FK={len(fk)}")
    if wal_size != 0 or journal_size != 0:
        raise RuntimeError(
            f"DỪNG: WAL/JOURNAL chưa sạch. wal={wal_size}; journal={journal_size}. "
            "Hãy dừng Uvicorn và chạy lại, không xóa file WAL thủ công."
        )

    need_person = {"id", "household_id", "full_name", "date_of_birth", "relationship_to_head", "is_active"}
    need_year = {"id", "survey_form_id", "survey_person_id", "school_year_id", "learning_status"}
    miss_person = sorted(need_person - person_cols)
    miss_year = sorted(need_year - year_cols)
    if miss_person or miss_year:
        raise RuntimeError(
            f"Schema không đúng nền. survey_people thiếu={miss_person}; "
            f"survey_person_year_records thiếu={miss_year}"
        )

    return integrity, len(fk), wal_size, journal_size, counts


def line_offsets(text: str) -> list[int]:
    offsets = [0]
    total = 0
    for line in text.splitlines(keepends=True):
        total += len(line)
        offsets.append(total)
    return offsets


def function_node(text: str, name: str):
    tree = ast.parse(text)
    nodes = [
        n for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name
    ]
    if len(nodes) != 1:
        raise RuntimeError(f"Cần đúng 1 hàm {name}; thực tế={len(nodes)}")
    return nodes[0]


def function_span(text: str, name: str) -> tuple[int, int]:
    node = function_node(text, name)
    if node.end_lineno is None:
        raise RuntimeError(f"Không xác định được cuối hàm {name}")
    offsets = line_offsets(text)
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
        raise RuntimeError("Không tìm thấy record_map trong helper Nhập nhanh")

    block = f'''    # === {MARK_HELPER}_START ===
    _fix28b_active_head_person = next(
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
        and _fix28b_active_head_person is None
    )
    # === {MARK_HELPER}_END ===

'''
    fn = fn.replace(anchor, block + anchor, 1)

    old = '            "full_name": "",\n'
    if old not in fn:
        raise RuntimeError("Không tìm thấy full_name mặc định trong person_form_data")
    fn = fn.replace(
        old,
        '''            "full_name": (
                household.head_name
                if household_head_needs_person
                else ""
            ),
''',
        1,
    )

    old = '            "relationship_to_head": "Con",\n'
    if old not in fn:
        raise RuntimeError("Không tìm thấy relationship_to_head mặc định")
    fn = fn.replace(
        old,
        '''            "relationship_to_head": (
                "Chủ hộ"
                if household_head_needs_person
                else "Con"
            ),
''',
        1,
    )

    old = '            "household": household,\n'
    if old not in fn:
        raise RuntimeError("Không tìm thấy household trong context Nhập nhanh")
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

    anchor = '    person.code = f"DT-{person.id:08d}"\n'
    pos = fn.find(anchor)
    if pos < 0:
        raise RuntimeError("Không tìm thấy điểm sau db.flush() của thành viên mới")
    insert_pos = pos + len(anchor)

    block = f'''

    # === {MARK_QUICK_ADD}_START ===
    _fix28b_year_id = int(survey_form.survey_batch.school_year_id)
    _fix28b_year_record = db.scalar(
        select(SurveyPersonYearRecord).where(
            SurveyPersonYearRecord.survey_form_id == survey_form.id,
            SurveyPersonYearRecord.survey_person_id == person.id,
            SurveyPersonYearRecord.school_year_id == _fix28b_year_id,
        )
    )
    if _fix28b_year_record is None:
        _fix28b_year_record = SurveyPersonYearRecord(
            survey_form_id=survey_form.id,
            survey_person_id=person.id,
            school_year_id=_fix28b_year_id,
            learning_status="CHUA_XAC_DINH",
        )
        db.add(_fix28b_year_record)
    # === {MARK_QUICK_ADD}_END ===
'''
    fn = fn[:insert_pos] + block + fn[insert_pos:]
    return replace_function(source, "them_doi_tuong_tu_nhap_nhanh", fn), "PATCHED"


def is_record_none_test(test: ast.AST) -> bool:
    if not isinstance(test, ast.Compare):
        return False
    if len(test.ops) != 1 or len(test.comparators) != 1:
        return False
    left = test.left
    comp = test.comparators[0]
    if not isinstance(left, ast.Name) or left.id != "record":
        return False
    if not isinstance(test.ops[0], (ast.Is, ast.Eq)):
        return False
    return isinstance(comp, ast.Constant) and comp.value is None


def patch_fix26g(source: str):
    fn_name = "fix26g_luu_chi_bao_nhanh"
    fn = get_function(source, fn_name)
    if MARK_FIX26G in fn:
        return source, "ALREADY_PRESENT", ""

    tree = ast.parse(fn)
    fn_node = next(n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)))
    all_names = {n.id for n in ast.walk(fn_node) if isinstance(n, ast.Name)}
    required_names = {"record", "survey_form", "person", "school_year_id", "db", "SurveyPersonYearRecord"}
    missing_names = sorted(required_names - all_names)
    if missing_names:
        raise RuntimeError(
            "FIX26G thiếu biến/model cần thiết để tạo year-record an toàn: "
            + repr(missing_names)
        )

    candidates = [
        n for n in ast.walk(fn_node)
        if isinstance(n, ast.If) and is_record_none_test(n.test)
    ]
    if not candidates:
        raise RuntimeError("Không tìm thấy 'if record is None' trong FIX26G")

    offsets = line_offsets(fn)
    diagnostics = []
    actionable = []
    already_capable = []

    for idx, node in enumerate(sorted(candidates, key=lambda x: x.lineno), start=1):
        if not node.body:
            continue
        first = node.body[0]
        last = node.body[-1]
        if last.end_lineno is None:
            continue
        body_start = offsets[first.lineno - 1] + first.col_offset
        body_end = offsets[last.end_lineno]
        body_text = fn[body_start:body_end]
        one_line = " ".join(body_text.strip().split())[:500]
        diagnostics.append(f"candidate#{idx}@L{node.lineno}: {one_line}")

        if "SurveyPersonYearRecord(" in body_text and "db.add(" in body_text:
            already_capable.append((node, body_start, body_end, body_text))
        else:
            actionable.append((node, body_start, body_end, body_text))

    if already_capable and not actionable:
        return source, "ALREADY_CAPABLE", " | ".join(diagnostics)

    # Chỉ sửa khi xác định duy nhất một nhánh thiếu record chưa có logic tạo.
    if len(actionable) != 1:
        raise RuntimeError(
            "Không khóa được duy nhất nhánh record is None của FIX26G. "
            + " | ".join(diagnostics)
        )

    node, body_start, body_end, body_text = actionable[0]
    if not node.body:
        raise RuntimeError("Nhánh record is None không có body")

    indent = " " * node.body[0].col_offset
    replacement = (
        f'{indent}# === {MARK_FIX26G}_START ===\n'
        f'{indent}record = SurveyPersonYearRecord(\n'
        f'{indent}    survey_form_id=survey_form.id,\n'
        f'{indent}    survey_person_id=person.id,\n'
        f'{indent}    school_year_id=school_year_id,\n'
        f'{indent}    learning_status="CHUA_XAC_DINH",\n'
        f'{indent})\n'
        f'{indent}db.add(record)\n'
        f'{indent}# === {MARK_FIX26G}_END ===\n'
    )

    fn = fn[:body_start] + replacement + fn[body_end:]
    ast.parse(fn)
    return replace_function(source, fn_name, fn), "PATCHED_AST", " | ".join(diagnostics)


def patch_quick_template(text: str):
    if MARK_UI in text:
        return text, "ALREADY_PRESENT"

    summary = "＋ Thêm thành viên mới"
    s_pos = text.find(summary)
    if s_pos < 0:
        raise RuntimeError("Không tìm thấy '＋ Thêm thành viên mới' trong quick_entry.html")

    details_pos = text.rfind("<details", 0, s_pos)
    if details_pos < 0:
        raise RuntimeError("Không tìm thấy <details> chứa form Thêm thành viên")
    details_end = text.find(">", details_pos)
    if details_end < 0 or details_end > s_pos:
        raise RuntimeError("Không khóa được thẻ mở <details> của form Thêm thành viên")

    opening = text[details_pos:details_end + 1]
    if UI_DETAILS_ID not in opening:
        opening_new = opening.replace("<details", f'<details id="{UI_DETAILS_ID}"', 1)
        text = text[:details_pos] + opening_new + text[details_end + 1:]
        delta = len(opening_new) - len(opening)
        s_pos += delta
        details_end += delta

    # Tìm lại vị trí sau khi đã thêm id.
    details_pos = text.rfind("<details", 0, s_pos)

    alert_block = f'''{{# === {MARK_UI}_START === #}}
            {{% if household_head_needs_person %}}
            <div class="pc-gv-v18-alert" style="margin-bottom:12px;">
                <strong>👤 Chủ hộ chưa có trong danh sách đối tượng điều tra.</strong><br>
                Hệ thống đã điền sẵn tên <strong>{{{{ household.head_name }}}}</strong>
                và quan hệ <strong>Chủ hộ</strong> ở biểu mẫu bên dưới.
                Hãy bổ sung Ngày sinh, Giới tính, Dân tộc và Số định danh nếu có.
                Nếu chủ hộ thuộc phạm vi 0–60 tuổi thì cần bổ sung để điều tra;
                nếu trên 60 tuổi có thể bỏ qua khi không thuộc phạm vi nghiệp vụ cần theo dõi.
            </div>
            <script>
            document.addEventListener("DOMContentLoaded", function () {{
                var el = document.getElementById("{UI_DETAILS_ID}");
                if (el) el.open = true;
            }});
            </script>
            {{% endif %}}
            {{# === {MARK_UI}_END === #}}

'''
    text = text[:details_pos] + alert_block + text[details_pos:]

    old_summary = "<summary>＋ Thêm thành viên mới</summary>"
    if old_summary in text:
        new_summary = '''<summary>
                    {% if household_head_needs_person %}
                        👤 Bổ sung chủ hộ vào đối tượng điều tra
                    {% else %}
                        ＋ Thêm thành viên mới
                    {% endif %}
                </summary>'''
        text = text.replace(old_summary, new_summary, 1)
    else:
        # Nếu summary được xuống dòng, chỉ đổi cụm chữ; giữ nguyên HTML hiện tại.
        text = text.replace(
            summary,
            '''{% if household_head_needs_person %}👤 Bổ sung chủ hộ vào đối tượng điều tra{% else %}＋ Thêm thành viên mới{% endif %}''',
            1,
        )

    return text, "PATCHED"


def verify_source(source: str):
    ast.parse(source)
    required = (
        MARK_HELPER,
        MARK_QUICK_ADD,
        '"household_head_needs_person": household_head_needs_person',
        'def fix26g_luu_chi_bao_nhanh(',
        'def them_doi_tuong_tu_nhap_nhanh(',
    )
    missing = [x for x in required if x not in source]
    if missing:
        raise RuntimeError("surveys.py sau sửa thiếu: " + repr(missing))

    fn = get_function(source, "fix26g_luu_chi_bao_nhanh")
    if MARK_FIX26G not in fn:
        # Cho phép nền hiện tại đã tự tạo record theo cách riêng.
        if not ("SurveyPersonYearRecord(" in fn and "db.add(" in fn):
            raise RuntimeError("FIX26G sau sửa vẫn chưa có logic tạo year-record")


def verify_template(text: str):
    required = (
        MARK_UI,
        UI_DETAILS_ID,
        "Chủ hộ chưa có trong danh sách đối tượng điều tra",
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
        log(f, "FIX 28B - TỰ TẠO HỒ SƠ NĂM HỌC + NHẮC BỔ SUNG CHỦ HỘ")
        log(f, "SỬA LỖI BỘ CÀI 28: KHÔNG PHỤ THUỘC CÂU THÔNG BÁO CŨ CỦA FIX26G")
        log(f, "SOURCE ONLY - KHÔNG GHI DATABASE TRONG LÚC CÀI")
        log(f, "=" * 165)

        for p in (DB, SURVEYS, QUICK):
            if not p.exists():
                raise RuntimeError(f"Không tìm thấy: {p}")

        db_sha_before = sha256_file(DB)
        log(f, "DB_SHA_BEFORE =", db_sha_before)
        if db_sha_before != EXPECTED_DB_SHA:
            raise RuntimeError(
                "DỪNG: DB SHA không còn đúng nền sau lần FIX28 dừng an toàn. "
                f"expected={EXPECTED_DB_SHA}; actual={db_sha_before}"
            )

        integrity, fk_count, wal_size, journal_size, counts = db_precheck()
        log(f, "INTEGRITY =", integrity)
        log(f, "FK_COUNT =", fk_count)
        log(f, "WAL_SIZE =", wal_size)
        log(f, "JOURNAL_SIZE =", journal_size)
        log(f, "CURRENT_COUNTS =", {
            "survey_people": int(counts[0] or 0),
            "year_records": int(counts[1] or 0),
            "active_people_missing_year2": int(counts[2] or 0),
        })

        source_before = SURVEYS.read_text(encoding="utf-8-sig")
        quick_before = QUICK.read_text(encoding="utf-8-sig")

        # Khóa các hàm bắt buộc trước khi chạm source.
        for fn_name in (
            "hien_thi_trang_nhap_nhanh",
            "them_doi_tuong_tu_nhap_nhanh",
            "fix26g_luu_chi_bao_nhanh",
        ):
            get_function(source_before, fn_name)

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_root = BACKUPS / f"source_truoc_FIX28B_{stamp}"
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
            source, s3, diag = patch_fix26g(source)
            quick, q1 = patch_quick_template(quick_before)

            log(f, "FIX26G_AST_DIAGNOSTIC =", diag)

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
            raise RuntimeError("DB thay đổi trong lúc cài source; source đã rollback")

        log(f, "DB_SHA_AFTER =", db_sha_after)
        log(f, "DATABASE_WRITES_THIS_RUN = 0")
        log(f, "FIX28B_SUCCESS = YES")
        log(f, "")
        log(f, "SAU KHI KHỞI ĐỘNG LẠI UVICORN:")
        log(f, " 1. Vào lại hộ đang kiểm thử -> Nhập nhanh.")
        log(f, " 2. Nếu chủ hộ chưa là SurveyPerson: khối bổ sung chủ hộ tự mở và điền sẵn Tên + Quan hệ Chủ hộ.")
        log(f, " 3. Thêm thành viên mới: hệ thống tạo ngay year-record của năm đợt điều tra.")
        log(f, " 4. Đối tượng cũ thiếu year-record: lần lưu chỉ báo/Nơi học đầu tiên qua FIX26G sẽ tự tạo record.")
        log(f, " 5. Không tự đoán ngày sinh/giới tính/dân tộc; không sửa dữ liệu cũ trong lúc cài.")
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
                log(f, "FIX28B_SUCCESS = NO")
                log(f, "ERROR =", repr(exc))
                if DB.exists():
                    log(f, "DB_SHA_CURRENT =", sha256_file(DB))
                log(f, "DỪNG AN TOÀN.")
                log(f, "=" * 165)
        except Exception:
            print("ERROR =", repr(exc))
        rc = 1
    raise SystemExit(rc)
