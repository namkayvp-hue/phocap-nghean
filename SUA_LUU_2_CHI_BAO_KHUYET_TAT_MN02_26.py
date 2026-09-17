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
YEAR_TEMPLATE = APP / "templates" / "surveys" / "year_records.html"
MODEL = APP / "survey_models.py"
BACKUPS = ROOT / "backups"
EXPORTS = ROOT / "exports"
OUT = EXPORTS / "SUA_LUU_2_CHI_BAO_KHUYET_TAT_MN02_26.txt"
MARK_START = "# === FIX26_SAVE_DISABILITY_REPORT_FLAGS_START ==="
MARK_END = "# === FIX26_SAVE_DISABILITY_REPORT_FLAGS_END ==="


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
    con = sqlite3.connect(
        f"file:{DB.as_posix()}?mode=ro",
        uri=True,
        timeout=30,
    )
    try:
        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
        fk_rows = con.execute("PRAGMA foreign_key_check").fetchall()
        cols = {
            str(r[1])
            for r in con.execute(
                'PRAGMA table_info("survey_person_year_records")'
            ).fetchall()
        }
        required = {
            "id",
            "survey_person_id",
            "school_year_id",
            "disability_status",
            "disability_can_learn",
            "disability_access_education",
        }
        missing = sorted(required - cols)
        if missing:
            raise RuntimeError("DB thiếu cột bắt buộc: " + ", ".join(missing))

        stats = con.execute(
            """
            SELECT
                COUNT(*),
                SUM(CASE WHEN disability_can_learn IS NULL THEN 1 ELSE 0 END),
                SUM(CASE WHEN disability_access_education IS NULL THEN 1 ELSE 0 END),
                SUM(CASE WHEN disability_can_learn = 1 THEN 1 ELSE 0 END),
                SUM(CASE WHEN disability_access_education = 1 THEN 1 ELSE 0 END)
            FROM survey_person_year_records
            WHERE disability_status = 'CO_KHUYET_TAT'
            """
        ).fetchone()
    finally:
        con.close()

    if integrity != "ok" or fk_rows:
        raise RuntimeError(
            f"DB health không đạt: integrity={integrity}; FK={len(fk_rows)}"
        )
    return integrity, len(fk_rows), tuple(int(x or 0) for x in stats)


def function_span(text: str, name: str) -> tuple[int, int]:
    tree = ast.parse(text)
    lines = text.splitlines(keepends=True)
    offsets = [0]
    total = 0
    for line in lines:
        total += len(line)
        offsets.append(total)

    nodes = [
        node for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == name
    ]
    if len(nodes) != 1:
        raise RuntimeError(f"Cần đúng 1 hàm {name}, thực tế={len(nodes)}")
    node = nodes[0]
    if node.end_lineno is None:
        raise RuntimeError(f"Không xác định được cuối hàm {name}")
    return offsets[node.lineno - 1], offsets[node.end_lineno]


def get_function(text: str, name: str) -> str:
    a, b = function_span(text, name)
    return text[a:b]


def replace_function(text: str, name: str, new_fn: str) -> str:
    a, b = function_span(text, name)
    return text[:a] + new_fn.rstrip() + "\n\n" + text[b:]


def ensure_params(fn: str) -> str:
    missing_can = "disability_can_learn: Annotated[str, Form()]" not in fn
    missing_access = "disability_access_education: Annotated[str, Form()]" not in fn
    if not missing_can and not missing_access:
        return fn

    m = re.search(
        r'^(?P<indent>[ \t]*)disability_status:\s*Annotated\[str,\s*Form\(\)\].*?\n',
        fn,
        flags=re.MULTILINE,
    )
    if m is None:
        raise RuntimeError("Không tìm thấy tham số disability_status")

    indent = m.group("indent")
    add = ""
    if missing_can:
        add += f'{indent}disability_can_learn: Annotated[str, Form()] = "",\n'
    if missing_access:
        add += f'{indent}disability_access_education: Annotated[str, Form()] = "",\n'
    return fn[:m.end()] + add + fn[m.end():]


def remove_old_fix(fn: str) -> str:
    pattern = re.compile(
        r'^[ \t]*# === FIX26_SAVE_DISABILITY_REPORT_FLAGS_START ===\n.*?'
        r'^[ \t]*# === FIX26_SAVE_DISABILITY_REPORT_FLAGS_END ===\n',
        flags=re.MULTILINE | re.DOTALL,
    )
    return pattern.sub("", fn)


def insert_parser(fn: str) -> str:
    m = re.search(
        r'^(?P<indent>[ \t]*)if disability_status not in DISABILITY_STATUS_LABELS:\n',
        fn,
        flags=re.MULTILINE,
    )
    if m is None:
        raise RuntimeError("Không tìm thấy kiểm tra DISABILITY_STATUS_LABELS")

    i = m.group("indent")
    lines = [
        f"{i}{MARK_START}",
        f"{i}disability_can_learn_value, disability_can_learn_error = chuyen_gia_tri_co_khong(",
        f"{i}    disability_can_learn,",
        f"{i}    \"Có khả năng học tập\",",
        f"{i})",
        f"{i}disability_access_education_value, disability_access_education_error = chuyen_gia_tri_co_khong(",
        f"{i}    disability_access_education,",
        f"{i}    \"Được tiếp cận giáo dục\",",
        f"{i})",
        f"{i}for disability_report_error in (",
        f"{i}    disability_can_learn_error,",
        f"{i}    disability_access_education_error,",
        f"{i}):",
        f"{i}    if disability_report_error:",
        f"{i}        errors.append(disability_report_error)",
        "",
        f"{i}if disability_status != \"CO_KHUYET_TAT\":",
        f"{i}    disability_can_learn_value = None",
        f"{i}    disability_access_education_value = None",
        f"{i}{MARK_END}",
        "",
    ]
    block = "\n".join(lines)
    return fn[:m.start()] + block + fn[m.start():]


def normalize_assignments(fn: str) -> str:
    # Xóa mọi phép gán cũ của đúng 2 trường trong hàm để tránh bị ghi đè lại.
    for pattern in (
        r'^[ \t]*form_record\.disability_can_learn\s*=.*?\n',
        r'^[ \t]*form_record\.disability_access_education\s*=.*?\n',
        r'^[ \t]*record\.disability_can_learn\s*=.*?\n',
        r'^[ \t]*record\.disability_access_education\s*=.*?\n',
    ):
        fn = re.sub(pattern, "", fn, flags=re.MULTILINE)

    error_pos = fn.find("    if errors:")
    if error_pos < 0:
        raise RuntimeError("Không tìm thấy nhánh if errors")

    return_pos = fn.find("        return templates.TemplateResponse(", error_pos)
    if return_pos < 0:
        raise RuntimeError("Không tìm thấy TemplateResponse trong nhánh lỗi")

    keep_values = (
        "        form_record.disability_can_learn = disability_can_learn_value\n"
        "        form_record.disability_access_education = disability_access_education_value\n\n"
    )
    fn = fn[:return_pos] + keep_values + fn[return_pos:]

    commit = re.search(
        r'^(?P<indent>[ \t]*)try:\n(?P=indent)[ \t]+db\.commit\(\)\n',
        fn,
        flags=re.MULTILINE,
    )
    if commit is None:
        raise RuntimeError("Không tìm thấy try/db.commit() của hàm lưu năm học")

    i = commit.group("indent")
    save_values = (
        f"{i}record.disability_can_learn = disability_can_learn_value\n"
        f"{i}record.disability_access_education = disability_access_education_value\n\n"
    )
    return fn[:commit.start()] + save_values + fn[commit.start():]


def patch_route(source: str) -> str:
    fn = get_function(source, "luu_theo_doi_nam_hoc")
    fn = remove_old_fix(fn)
    fn = ensure_params(fn)
    fn = insert_parser(fn)
    fn = normalize_assignments(fn)
    return replace_function(source, "luu_theo_doi_nam_hoc", fn)


def verify_ui_and_model():
    template = YEAR_TEMPLATE.read_text(encoding="utf-8-sig")
    for token in (
        'name="disability_can_learn"',
        'name="disability_access_education"',
        "selected_record.disability_can_learn",
        "selected_record.disability_access_education",
    ):
        if token not in template:
            raise RuntimeError("year_records.html thiếu: " + token)

    model = MODEL.read_text(encoding="utf-8-sig")
    for token in ("disability_can_learn", "disability_access_education"):
        if token not in model:
            raise RuntimeError("survey_models.py thiếu: " + token)


def verify_route():
    source = SURVEYS.read_text(encoding="utf-8")
    ast.parse(source)
    fn = get_function(source, "luu_theo_doi_nam_hoc")
    required = (
        MARK_START,
        "disability_can_learn: Annotated[str, Form()]",
        "disability_access_education: Annotated[str, Form()]",
        "form_record.disability_can_learn = disability_can_learn_value",
        "form_record.disability_access_education = disability_access_education_value",
        "record.disability_can_learn = disability_can_learn_value",
        "record.disability_access_education = disability_access_education_value",
    )
    for token in required:
        if token not in fn:
            raise RuntimeError("Hàm lưu sau sửa thiếu: " + token)

    if fn.count("record.disability_can_learn = disability_can_learn_value") != 1:
        raise RuntimeError("record.disability_can_learn không còn đúng 1 phép gán")
    if fn.count("record.disability_access_education = disability_access_education_value") != 1:
        raise RuntimeError("record.disability_access_education không còn đúng 1 phép gán")


def clear_cache():
    for cache in APP.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)


def main() -> int:
    EXPORTS.mkdir(parents=True, exist_ok=True)
    BACKUPS.mkdir(parents=True, exist_ok=True)

    with OUT.open("w", encoding="utf-8-sig", newline="\n") as f:
        log(f, "=" * 150)
        log(f, "SỬA LỖI 26 - LƯU 2 CHỈ BÁO KHUYẾT TẬT PHỤC VỤ MN-02")
        log(f, "Có khả năng học tập + Được tiếp cận giáo dục")
        log(f, "CHỈ SỬA SOURCE. KHÔNG GHI DATABASE.")
        log(f, "=" * 150)

        for p in (DB, SURVEYS, YEAR_TEMPLATE, MODEL):
            if not p.exists():
                raise RuntimeError(f"Không tìm thấy: {p}")

        integrity, fk_count, stats = db_precheck()
        db_sha_before = sha256_file(DB)
        log(f, "DB_SHA_BEFORE =", db_sha_before)
        log(f, "INTEGRITY =", integrity)
        log(f, "FK_COUNT =", fk_count)
        log(f, "DISABLED_ROWS_BEFORE =", {
            "total": stats[0],
            "can_learn_null": stats[1],
            "access_education_null": stats[2],
            "can_learn_yes": stats[3],
            "access_education_yes": stats[4],
        })

        verify_ui_and_model()
        log(f, "UI_MODEL_CHECK = PASS")

        source_before = SURVEYS.read_text(encoding="utf-8-sig")
        if "def luu_theo_doi_nam_hoc(" not in source_before:
            raise RuntimeError("Không tìm thấy hàm luu_theo_doi_nam_hoc")

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = BACKUPS / f"source_truoc_FIX26_{stamp}"
        backup_file = backup_dir / SURVEYS.relative_to(ROOT)
        backup_file.parent.mkdir(parents=True, exist_ok=False)
        shutil.copy2(SURVEYS, backup_file)
        log(f, "SOURCE_BACKUP =", backup_dir)

        try:
            source_after = patch_route(source_before)
            SURVEYS.write_text(source_after, encoding="utf-8")
            py_compile.compile(str(SURVEYS), doraise=True)
            verify_route()
            clear_cache()
            log(f, "PY_COMPILE = PASS")
            log(f, "SAVE_ROUTE_VERIFY = PASS")
        except Exception:
            shutil.copy2(backup_file, SURVEYS)
            clear_cache()
            log(f, "ROLLBACK_SOURCE = PASS")
            raise

        db_sha_after = sha256_file(DB)
        if db_sha_after != db_sha_before:
            shutil.copy2(backup_file, SURVEYS)
            clear_cache()
            raise RuntimeError("DB SHA thay đổi ngoài dự kiến; source đã khôi phục")

        log(f, "DB_SHA_AFTER =", db_sha_after)
        log(f, "DATABASE_WRITES_THIS_RUN = 0")
        log(f, "")
        log(f, "SAU KHI CÀI:")
        log(f, " 1. Khởi động lại Uvicorn và Ctrl+F5.")
        log(f, " 2. Mở lại hồ sơ trẻ khuyết tật.")
        log(f, " 3. Chọn lại 'Có khả năng học tập' và 'Được tiếp cận giáo dục'.")
        log(f, " 4. Bấm Lưu và mở lại hồ sơ để kiểm tra lựa chọn còn nguyên.")
        log(f, " 5. Xuất lại MN-02.")
        log(f, "")
        log(f, "LƯU Ý: Không tự suy đoán/backfill hồ sơ cũ đang NULL.")
        log(f, "FIX26_SUCCESS = YES")
        log(f, "=" * 150)

    return 0


if __name__ == "__main__":
    try:
        rc = main()
    except Exception as exc:
        EXPORTS.mkdir(parents=True, exist_ok=True)
        try:
            with OUT.open("a", encoding="utf-8-sig", newline="\n") as f:
                log(f, "")
                log(f, "=" * 150)
                log(f, "FIX26_SUCCESS = NO")
                log(f, "ERROR =", repr(exc))
                if DB.exists():
                    log(f, "DB_SHA_CURRENT =", sha256_file(DB))
                log(f, "DỪNG AN TOÀN.")
                log(f, "=" * 150)
        except Exception:
            print("ERROR =", repr(exc))
        rc = 1
    raise SystemExit(rc)
