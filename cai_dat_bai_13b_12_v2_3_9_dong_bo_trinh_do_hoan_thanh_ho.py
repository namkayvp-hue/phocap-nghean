# -*- coding: utf-8 -*-
from __future__ import annotations
import ast
import py_compile
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from jinja2 import Environment

PROJECT = Path(r"C:\PhoCap")
APP = PROJECT / "app"
DB = PROJECT / "data" / "phocap.db"
EXPORTS = PROJECT / "exports"
SURVEYS = APP / "routers" / "surveys.py"
YEAR_TEMPLATE = APP / "templates" / "surveys" / "year_records.html"

FUNC_NAME = "luu_theo_doi_nam_hoc"
STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = EXPORTS / f"backup_bai_13b_12_v2_3_9_{STAMP}"
DB_BACKUP = BACKUP / "phocap.db"
REPORT = EXPORTS / f"bao_cao_cai_bai_13b_12_v2_3_9_{STAMP}.txt"

MARKER_BACKEND = "BAI_13B_12_V2_3_9_AUTO_FINISH_HOUSEHOLD_START"
MARKER_UI = "BAI_13B_12_V2_3_9_DERIVED_GRADE_UI_START"
MARKER_IMPORT = "BAI_13B_12_V2_3_9_DATETIME_ALIASES"

DERIVED_UI = '\n<!-- === BAI_13B_12_V2_3_9_DERIVED_GRADE_UI_START === -->\n<script>\n(function () {\n    "use strict";\n    function syncGradeFlags() {\n        const highest = document.getElementById("highest_completed_grade");\n        const g3 = document.getElementById("completed_grade_3");\n        const g5 = document.getElementById("completed_grade_5");\n        if (!highest || !g3 || !g5) return;\n\n        const raw = String(highest.value || "").trim();\n        const grade = raw === "" ? null : Number(raw);\n\n        if (grade === null || !Number.isFinite(grade)) {\n            g3.value = "";\n            g5.value = "";\n        } else {\n            g3.value = grade >= 3 ? "CO" : "KHONG";\n            g5.value = grade >= 5 ? "CO" : "KHONG";\n        }\n\n        g3.disabled = true;\n        g5.disabled = true;\n        g3.setAttribute("aria-disabled", "true");\n        g5.setAttribute("aria-disabled", "true");\n    }\n\n    document.addEventListener("DOMContentLoaded", function () {\n        const highest = document.getElementById("highest_completed_grade");\n        if (highest) {\n            highest.addEventListener("change", syncGradeFlags);\n            highest.addEventListener("input", syncGradeFlags);\n        }\n        syncGradeFlags();\n        window.setTimeout(syncGradeFlags, 100);\n        window.setTimeout(syncGradeFlags, 400);\n    });\n})();\n</script>\n<!-- === BAI_13B_12_V2_3_9_DERIVED_GRADE_UI_END === -->\n<!-- === BAI_13B_12_V2_3_9_FINISH_BUTTON_WIRING_START === -->\n<script>\n(function () {\n    "use strict";\n    document.addEventListener("DOMContentLoaded", function () {\n        Array.from(document.querySelectorAll(\'button[type="submit"]\'))\n            .forEach(function (button) {\n                const text = String(button.textContent || "")\n                    .replace(/\\s+/g, " ")\n                    .trim();\n                if (text.includes("Lưu thành viên cuối và hoàn thành hộ")) {\n                    button.name = "finish_household";\n                    button.value = "1";\n                }\n            });\n    });\n})();\n</script>\n<!-- === BAI_13B_12_V2_3_9_FINISH_BUTTON_WIRING_END === -->\n'
AUTO_FINISH_BLOCK = '\n__INDENT__# === BAI_13B_12_V2_3_9_AUTO_FINISH_HOUSEHOLD_START ===\n__INDENT___b13239_household_completed = False\n__INDENT___b13239_finish_requested = (\n__INDENT__    str(finish_household or "").strip() == "1"\n__INDENT__    and str(\n__INDENT__        lay_thong_tin_nguoi_dung(request).get("role_code") or ""\n__INDENT__    ).strip().upper() == "GIAO_VIEN"\n__INDENT__)\n__INDENT__\n__INDENT__if _b13239_finish_requested:\n__INDENT__    db.flush()\n__INDENT__    _b13239_completion = b131133_danh_gia_do_day_du_phieu_nhap_nhanh(\n__INDENT__        db=db,\n__INDENT__        survey_form=survey_form,\n__INDENT__    )\n__INDENT__    _b13239_active = int(_b13239_completion.get("active_people_count", 0) or 0)\n__INDENT__    _b13239_missing = int(_b13239_completion.get("missing_year_record_count", 0) or 0)\n__INDENT__    _b13239_incomplete = int(_b13239_completion.get("incomplete_year_record_count", 0) or 0)\n__INDENT__\n__INDENT__    if _b13239_active > 0 and _b13239_missing == 0 and _b13239_incomplete == 0:\n__INDENT__        survey_form.status = "DA_HOAN_THANH"\n__INDENT__        if survey_form.survey_date is None:\n__INDENT__            survey_form.survey_date = _b13239_date.today()\n__INDENT__        _b13239_head_name = str(\n__INDENT__            getattr(survey_form.household, "head_name", "")\n__INDENT__            or getattr(survey_form, "head_name_snapshot", "")\n__INDENT__            or ""\n__INDENT__        ).strip()\n__INDENT__        if _b13239_head_name:\n__INDENT__            survey_form.household_representative_name = _b13239_head_name\n__INDENT__        if survey_form.household_confirmed_at is None:\n__INDENT__            survey_form.household_confirmed_at = _b13239_datetime.now()\n__INDENT__        _b13239_household_completed = True\n__INDENT__# === BAI_13B_12_V2_3_9_AUTO_FINISH_HOUSEHOLD_END ===\n'
AFTER_COMMIT_BLOCK = '\n__INDENT__if _b13239_household_completed:\n__INDENT__    return RedirectResponse(\n__INDENT__        url=(\n__INDENT__            f"/dieu-tra/{batch_id}/ho-dan"\n__INDENT__            f"?school_year_id={school_year_id}"\n__INDENT__            "&status=household_auto_completed"\n__INDENT__        ),\n__INDENT__        status_code=303,\n__INDENT__    )\n'
OLD_LAST_BUTTON = '                        {% if next_person_url %}\n                            Lưu và chuyển thành viên tiếp theo\n                        {% else %}\n                            Lưu thành viên cuối\n                        {% endif %}\n'
NEW_LAST_BUTTON = '                        {% if next_person_url %}\n                            Lưu và chuyển thành viên tiếp theo\n                        {% else %}\n                            ✓ Lưu thành viên cuối và hoàn thành hộ\n                        {% endif %}\n'
STATUS_NEEDLE = '    "year_record_saved": (\n        "Đã lưu thông tin theo dõi năm học thành công."\n    ),\n'
STATUS_REPLACEMENT = '    "year_record_saved": (\n        "Đã lưu thông tin theo dõi năm học thành công."\n    ),\n    "household_auto_completed": (\n        "Đã lưu thành viên cuối và hoàn thành hộ dân thành công."\n    ),\n'

def read_text(path):
    return path.read_text(encoding="utf-8-sig")

def write_text(path, value):
    path.write_text(value, encoding="utf-8")

def backup_file(path):
    target = BACKUP / path.relative_to(PROJECT)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, target)

def restore_file(path):
    source = BACKUP / path.relative_to(PROJECT)
    if source.exists():
        shutil.copy2(source, path)

def backup_db():
    src = sqlite3.connect(str(DB))
    dst = sqlite3.connect(str(DB_BACKUP))
    try:
        src.backup(dst)
        dst.commit()
    finally:
        dst.close()
        src.close()

def restore_db():
    if not DB_BACKUP.exists():
        return
    src = sqlite3.connect(str(DB_BACKUP))
    dst = sqlite3.connect(str(DB))
    try:
        src.backup(dst)
        dst.commit()
    finally:
        dst.close()
        src.close()

def db_state():
    con = sqlite3.connect(str(DB))
    try:
        return {
            "integrity": str(con.execute("PRAGMA integrity_check").fetchone()[0]),
            "fk_count": len(con.execute("PRAGMA foreign_key_check").fetchall()),
            "people": int(con.execute("SELECT COUNT(*) FROM survey_people").fetchone()[0]),
            "year_records": int(con.execute("SELECT COUNT(*) FROM survey_person_year_records").fetchone()[0]),
            "forms": int(con.execute("SELECT COUNT(*) FROM survey_forms").fetchone()[0]),
        }
    finally:
        con.close()

def find_function(source):
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == FUNC_NAME:
            return node
    raise RuntimeError(f"Không tìm thấy hàm {FUNC_NAME}.")

def ensure_datetime_alias_import(source):
    if MARKER_IMPORT in source:
        return source
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    insert_line = 0
    if (
        tree.body
        and isinstance(tree.body[0], ast.Expr)
        and isinstance(tree.body[0].value, ast.Constant)
        and isinstance(tree.body[0].value.value, str)
    ):
        insert_line = int(getattr(tree.body[0], "end_lineno", tree.body[0].lineno))
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == "__future__":
            insert_line = max(insert_line, int(getattr(node, "end_lineno", node.lineno)))
    lines.insert(
        insert_line,
        "# === BAI_13B_12_V2_3_9_DATETIME_ALIASES ===\n"
        "from datetime import date as _b13239_date, datetime as _b13239_datetime\n"
    )
    result = "".join(lines)
    ast.parse(result)
    return result

def patch_status_message(source):
    if '"household_auto_completed"' in source:
        return source
    if STATUS_NEEDLE not in source:
        raise RuntimeError("Không tìm thấy STATUS_MESSAGES year_record_saved.")
    return source.replace(STATUS_NEEDLE, STATUS_REPLACEMENT, 1)

def patch_function_signature(source):
    fn = find_function(source)
    lines = source.splitlines(keepends=True)
    start = int(fn.lineno) - 1
    end = min(len(lines), start + 120)
    if any("finish_household:" in lines[i] for i in range(start, end)):
        return source
    target = None
    for i in range(start, end):
        if "db: Session = Depends(get_db)," in lines[i]:
            target = i
            break
    if target is None:
        raise RuntimeError("Không tìm thấy tham số db trong header route.")
    indent = lines[target][:len(lines[target]) - len(lines[target].lstrip())]
    lines.insert(target, indent + 'finish_household: Annotated[str | None, Form()] = None,\n')
    result = "".join(lines)
    ast.parse(result)
    return result

def find_commits(source):
    fn = find_function(source)
    commits = []
    for node in ast.walk(fn):
        if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
            continue
        func = node.value.func
        if (
            isinstance(func, ast.Attribute)
            and func.attr == "commit"
            and isinstance(func.value, ast.Name)
            and func.value.id == "db"
        ):
            commits.append(node)
    return sorted(commits, key=lambda n: n.lineno)

def patch_final_commit(source):
    if MARKER_BACKEND in source:
        return source
    for token in (
        "BAI_13B_12_V2_3_GRADE_TO_XMC_START",
        "record.completed_grade_3 = (",
        "record.completed_grade_5 = (",
        "b131133_danh_gia_do_day_du_phieu_nhap_nhanh",
    ):
        if token not in source:
            raise RuntimeError("Thiếu nền V2.3.x: " + token)

    commits = find_commits(source)
    if not commits:
        raise RuntimeError("Không tìm thấy db.commit() trong route lưu năm học.")

    commit = commits[-1]
    lines = source.splitlines(keepends=True)
    idx = int(commit.lineno) - 1
    indent = lines[idx][:len(lines[idx]) - len(lines[idx].lstrip())]
    lines.insert(idx, AUTO_FINISH_BLOCK.replace("__INDENT__", indent))
    temp = "".join(lines)
    ast.parse(temp)

    commits2 = find_commits(temp)
    commit2 = commits2[-1]
    lines2 = temp.splitlines(keepends=True)
    idx2 = int(commit2.lineno) - 1
    lines2.insert(idx2 + 1, AFTER_COMMIT_BLOCK.replace("__INDENT__", indent))
    result = "".join(lines2)
    ast.parse(result)
    return result

def patch_template(source):
    if MARKER_UI in source:
        return source
    if OLD_LAST_BUTTON not in source:
        raise RuntimeError("Không tìm thấy nhãn nút thành viên cuối đúng bản khảo sát.")
    source = source.replace(OLD_LAST_BUTTON, NEW_LAST_BUTTON, 1)
    pos = source.rfind("</body>")
    if pos < 0:
        raise RuntimeError("year_records.html thiếu </body>.")
    return source[:pos] + DERIVED_UI + source[pos:]

def verify_source():
    surveys = read_text(SURVEYS)
    template = read_text(YEAR_TEMPLATE)

    for token in (
        MARKER_BACKEND,
        'finish_household: Annotated[str | None, Form()] = None',
        'survey_form.status = "DA_HOAN_THANH"',
        "survey_form.household_representative_name",
        "survey_form.household_confirmed_at",
        "BAI_13B_12_V2_3_GRADE_TO_XMC_START",
        "_b1312v21_grade_value >= 3",
        "_b1312v21_grade_value >= 5",
        "BAI_13B_11_15_2_4_7_1B_DERIVE_LITERACY_STATUS_START",
    ):
        if token not in surveys:
            raise RuntimeError("Verifier thiếu backend: " + token)

    for token in (
        MARKER_UI,
        "Lưu thành viên cuối và hoàn thành hộ",
        'button.name = "finish_household"',
        'g3.disabled = true',
        'g5.disabled = true',
    ):
        if token not in template:
            raise RuntimeError("Verifier thiếu template: " + token)

    ast.parse(surveys)
    py_compile.compile(str(SURVEYS), doraise=True)
    Environment().parse(template)

def main():
    print("=" * 122)
    print("BÀI 13B-12 V2.3.9 - ĐỒNG BỘ TRÌNH ĐỘ + HOÀN THÀNH HỘ MỘT THAO TÁC")
    print("=" * 122)

    for path in (DB, SURVEYS, YEAR_TEMPLATE):
        if not path.exists():
            print("DỪNG AN TOÀN: thiếu", path)
            return 2

    before = db_state()
    print("integrity_check:", before["integrity"])
    print("foreign_key_check:", before["fk_count"], "lỗi")
    if before["integrity"].lower() != "ok" or before["fk_count"] != 0:
        print("DỪNG: database chưa đạt kiểm tra.")
        return 3

    surveys = read_text(SURVEYS)
    template = read_text(YEAR_TEMPLATE)

    for token in (
        "BAI_13B_12_V2_3_GRADE_TO_XMC_START",
        "BAI_13B_11_15_2_4_7_1B_DERIVE_LITERACY_STATUS_START",
        "b131133_danh_gia_do_day_du_phieu_nhap_nhanh",
    ):
        if token not in surveys:
            print("DỪNG AN TOÀN: thiếu nền", token)
            return 4
    if 'id="highest_completed_grade"' not in template:
        print("DỪNG AN TOÀN: thiếu field highest_completed_grade.")
        return 4

    if MARKER_BACKEND in surveys and MARKER_UI in template:
        print("V2.3.9 đã cài. Không cài lặp.")
        return 0

    try:
        new_surveys = ensure_datetime_alias_import(surveys)
        new_surveys = patch_status_message(new_surveys)
        new_surveys = patch_function_signature(new_surveys)
        new_surveys = patch_final_commit(new_surveys)
        new_template = patch_template(template)
        ast.parse(new_surveys)
        Environment().parse(new_template)
    except Exception as exc:
        print()
        print("DỪNG AN TOÀN TRƯỚC KHI GHI FILE:")
        print(type(exc).__name__ + ":", exc)
        return 5

    EXPORTS.mkdir(parents=True, exist_ok=True)
    BACKUP.mkdir(parents=True, exist_ok=False)
    backup_file(SURVEYS)
    backup_file(YEAR_TEMPLATE)
    backup_db()
    print("Backup:", BACKUP)

    try:
        write_text(SURVEYS, new_surveys)
        write_text(YEAR_TEMPLATE, new_template)
        verify_source()

        after = db_state()
        if after["integrity"].lower() != "ok":
            raise RuntimeError("integrity_check không đạt sau cài.")
        if after["fk_count"] != 0:
            raise RuntimeError("foreign_key_check có lỗi sau cài.")
        if after["people"] != before["people"]:
            raise RuntimeError("Số nhân khẩu thay đổi ngoài dự kiến.")
        if after["year_records"] != before["year_records"]:
            raise RuntimeError("Số year-record thay đổi ngoài dự kiến.")
        if after["forms"] != before["forms"]:
            raise RuntimeError("Số phiếu thay đổi ngoài dự kiến.")

        for cache in APP.rglob("__pycache__"):
            if cache.is_dir():
                shutil.rmtree(cache, ignore_errors=True)

    except Exception as exc:
        print()
        print("CÓ LỖI - ĐANG ROLLBACK SOURCE + DATABASE...")
        print(type(exc).__name__ + ":", exc)
        restore_file(SURVEYS)
        restore_file(YEAR_TEMPLATE)
        restore_db()
        print("ĐÃ KHÔI PHỤC.")
        return 9

    REPORT.write_text(
        "\n".join([
            "=" * 122,
            "BÁO CÁO CÀI BÀI 13B-12 V2.3.9",
            "=" * 122,
            f"Thời gian: {datetime.now():%d/%m/%Y %H:%M:%S}",
            "",
            "TRÌNH ĐỘ/XMC:",
            "- Giữ nguyên backend Grade -> completed_grade_3/5.",
            "- Lớp cao nhất đã hoàn thành là dữ liệu gốc.",
            "- Hai chỉ báo lớp 3/lớp 5 chỉ hiển thị kết quả suy ra.",
            "",
            "HOÀN THÀNH HỘ:",
            "- Thành viên cuối: một nút Lưu + hoàn thành hộ.",
            "- Nếu toàn hộ đủ: DA_HOAN_THANH + ngày điều tra + người đại diện chủ hộ + xác nhận hộ.",
            "- Quay về danh sách hộ sau khi hoàn thành.",
            "",
            "Không tự sửa dữ liệu hiện có trong lúc cài.",
            f"integrity_check: {after['integrity']}",
            f"foreign_key_check: {after['fk_count']} lỗi",
            f"Backup: {BACKUP}",
        ]) + "\n",
        encoding="utf-8-sig",
    )

    print()
    print("=" * 122)
    print("CÀI ĐẶT THÀNH CÔNG BÀI 13B-12 V2.3.9")
    print("=" * 122)
    print(" - Lớp 3/lớp 5 đã khóa theo Lớp cao nhất.")
    print(" - Thành viên cuối có một nút lưu và hoàn thành hộ.")
    print("Báo cáo:", REPORT)
    print("Backup:", BACKUP)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
