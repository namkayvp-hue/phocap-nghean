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
OUT = EXPORTS / "SUA_LUU_NOI_HOC_VA_KHUYET_TAT_26C.txt"

FIX_MARK = "FIX26C_FINAL_SAVE_STUDY_LOCATION_AND_DISABILITY"


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
        fk = con.execute("PRAGMA foreign_key_check").fetchall()
        cols = {
            str(r[1])
            for r in con.execute(
                'PRAGMA table_info("survey_person_year_records")'
            ).fetchall()
        }
        current = con.execute(
            """
            SELECT
                COUNT(*),
                SUM(
                    CASE
                        WHEN study_location_scope IS NULL
                             OR TRIM(COALESCE(study_location_scope,'')) = ''
                        THEN 1 ELSE 0
                    END
                ),
                SUM(
                    CASE
                        WHEN disability_status='CO_KHUYET_TAT'
                             AND disability_can_learn IS NULL
                        THEN 1 ELSE 0
                    END
                ),
                SUM(
                    CASE
                        WHEN disability_status='CO_KHUYET_TAT'
                             AND disability_access_education IS NULL
                        THEN 1 ELSE 0
                    END
                )
            FROM survey_person_year_records
            """
        ).fetchone()
    finally:
        con.close()

    required = {
        "study_location_scope",
        "disability_status",
        "disability_can_learn",
        "disability_access_education",
    }
    missing = sorted(required - cols)
    if missing:
        raise RuntimeError(
            "DB thiếu cột bắt buộc: " + ", ".join(missing)
        )

    if integrity != "ok" or fk:
        raise RuntimeError(
            f"DB health không đạt: integrity={integrity}, FK={len(fk)}"
        )

    return integrity, len(fk), tuple(int(x or 0) for x in current)


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
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        and n.name == name
    ]
    if len(nodes) != 1:
        raise RuntimeError(
            f"Cần đúng 1 hàm {name}, thực tế={len(nodes)}."
        )

    node = nodes[0]
    if node.end_lineno is None:
        raise RuntimeError(
            f"Không xác định được cuối hàm {name}."
        )

    return offsets[node.lineno - 1], offsets[node.end_lineno]


def get_function(text: str, name: str) -> str:
    a, b = function_span(text, name)
    return text[a:b]


def replace_function(text: str, name: str, fn: str) -> str:
    a, b = function_span(text, name)
    return text[:a] + fn.rstrip() + "\n\n" + text[b:]


def remove_old_fix_blocks(fn: str) -> str:
    patterns = [
        r'^[ \t]*# === FIX26_SAVE_DISABILITY_REPORT_FLAGS_START ===\n.*?'
        r'^[ \t]*# === FIX26_SAVE_DISABILITY_REPORT_FLAGS_END ===\n',
        r'^[ \t]*# === FIX26A_SAVE_DISABILITY_REPORT_FLAGS_START ===\n.*?'
        r'^[ \t]*# === FIX26A_SAVE_DISABILITY_REPORT_FLAGS_END ===\n',
        r'^[ \t]*# === FIX26B_SAVE_DISABILITY_REPORT_FLAGS_START ===\n.*?'
        r'^[ \t]*# === FIX26B_SAVE_DISABILITY_REPORT_FLAGS_END ===\n',
        r'^[ \t]*# === FIX26A_FINAL_ASSIGN_BEFORE_COMMIT ===\n'
        r'(?:^[ \t]*record\.disability_can_learn.*\n)?'
        r'(?:^[ \t]*record\.disability_access_education.*\n)?',
        r'^[ \t]*# === FIX26B_FINAL_ASSIGN_BEFORE_COMMIT ===\n'
        r'(?:^[ \t]*record\.disability_can_learn.*\n)?'
        r'(?:^[ \t]*record\.disability_access_education.*\n)?',
        r'^[ \t]*# === FIX26C_FINAL_SAVE_STUDY_LOCATION_AND_DISABILITY ===\n.*?'
        r'^[ \t]*# === END FIX26C_FINAL_SAVE_STUDY_LOCATION_AND_DISABILITY ===\n',
    ]
    for pattern in patterns:
        fn = re.sub(
            pattern,
            "",
            fn,
            flags=re.M | re.S,
        )
    return fn


def ensure_params(fn: str) -> str:
    need_study = (
        "study_location_scope: Annotated[str, Form()]"
        not in fn
    )
    need_can = (
        "disability_can_learn: Annotated[str, Form()]"
        not in fn
    )
    need_access = (
        "disability_access_education: Annotated[str, Form()]"
        not in fn
    )

    if not any((need_study, need_can, need_access)):
        return fn

    m = re.search(
        r'^(?P<i>[ \t]*)disability_status:\s*Annotated\[str,\s*Form\(\)\]'
        r'.*?\n',
        fn,
        flags=re.M,
    )
    if not m:
        raise RuntimeError(
            "Không tìm thấy tham số disability_status để chèn các field còn thiếu."
        )

    indent = m.group("i")
    before = ""
    after = ""

    if need_study:
        before += (
            f'{indent}study_location_scope: '
            'Annotated[str, Form()] = "",\n'
        )
    if need_can:
        after += (
            f'{indent}disability_can_learn: '
            'Annotated[str, Form()] = "",\n'
        )
    if need_access:
        after += (
            f'{indent}disability_access_education: '
            'Annotated[str, Form()] = "",\n'
        )

    return (
        fn[:m.start()]
        + before
        + fn[m.start():m.end()]
        + after
        + fn[m.end():]
    )


def remove_overwriting_assignments(fn: str) -> str:
    patterns = (
        r'^[ \t]*(?:form_record|record)\.study_location_scope\s*=.*?\n',
        r'^[ \t]*(?:form_record|record)\.disability_can_learn\s*=.*?\n',
        r'^[ \t]*(?:form_record|record)\.disability_access_education\s*=.*?\n',
    )
    for pattern in patterns:
        fn = re.sub(
            pattern,
            "",
            fn,
            flags=re.M,
        )
    return fn


def insert_final_save_block(fn: str) -> tuple[str, int]:
    commits = list(re.finditer(
        r'^(?P<i>[ \t]*)db\.commit\(\)\s*$',
        fn,
        flags=re.M,
    ))
    if not commits:
        raise RuntimeError(
            "Không tìm thấy db.commit() trong hàm luu_theo_doi_nam_hoc."
        )

    m = commits[-1]
    i = m.group("i")

    block = f"""{i}# === {FIX_MARK} ===
{i}# 1) Nơi học: lưu trực tiếp mã select hiện tại.
{i}_fix26c_study = str(study_location_scope or "").strip().upper()
{i}_fix26c_study_allowed = {{
{i}    "",
{i}    "CHUA_XAC_DINH",
{i}    "TAI_CHO",
{i}    "DI_HOC_TRONG_TINH",
{i}    "DI_HOC_NGOAI_TINH",
{i}    "DI_HOC_NOI_KHAC",
{i}    "NOI_KHAC_DEN",
{i}}}
{i}if _fix26c_study not in _fix26c_study_allowed:
{i}    _fix26c_study = ""
{i}record.study_location_scope = _fix26c_study or None
{i}
{i}# 2) Hai chỉ báo khuyết tật: chuyển chuỗi form -> Boolean/None.
{i}def _fix26c_bool(raw_value):
{i}    _raw = str(raw_value or "").strip().lower()
{i}    if _raw in {{"1", "true", "yes", "y", "co", "có"}}:
{i}        return True
{i}    if _raw in {{"0", "false", "no", "n", "khong", "không"}}:
{i}        return False
{i}    return None
{i}
{i}_fix26c_can = _fix26c_bool(disability_can_learn)
{i}_fix26c_access = _fix26c_bool(disability_access_education)
{i}
{i}if str(disability_status or "").strip().upper() == "CO_KHUYET_TAT":
{i}    record.disability_can_learn = _fix26c_can
{i}    record.disability_access_education = _fix26c_access
{i}else:
{i}    record.disability_can_learn = None
{i}    record.disability_access_education = None
{i}
{i}if "form_record" in locals() and form_record is not None:
{i}    if hasattr(form_record, "study_location_scope"):
{i}        form_record.study_location_scope = record.study_location_scope
{i}    if hasattr(form_record, "disability_can_learn"):
{i}        form_record.disability_can_learn = record.disability_can_learn
{i}    if hasattr(form_record, "disability_access_education"):
{i}        form_record.disability_access_education = record.disability_access_education
{i}# === END {FIX_MARK} ===
"""

    return fn[:m.start()] + block + fn[m.start():], len(commits)


def patch_source(source: str) -> tuple[str, int]:
    fn = get_function(
        source,
        "luu_theo_doi_nam_hoc",
    )
    fn = remove_old_fix_blocks(fn)
    fn = ensure_params(fn)
    fn = remove_overwriting_assignments(fn)
    fn, commit_count = insert_final_save_block(fn)

    return (
        replace_function(
            source,
            "luu_theo_doi_nam_hoc",
            fn,
        ),
        commit_count,
    )


def verify_ui_model():
    template = YEAR_TEMPLATE.read_text(
        encoding="utf-8-sig"
    )
    model = MODEL.read_text(
        encoding="utf-8-sig"
    )

    required_template = (
        'name="study_location_scope"',
        'name="disability_can_learn"',
        'name="disability_access_education"',
    )
    missing_template = [
        x for x in required_template
        if x not in template
    ]
    if missing_template:
        raise RuntimeError(
            "year_records.html thiếu: "
            + repr(missing_template)
        )

    required_model = (
        "study_location_scope",
        "disability_can_learn",
        "disability_access_education",
    )
    missing_model = [
        x for x in required_model
        if x not in model
    ]
    if missing_model:
        raise RuntimeError(
            "survey_models.py thiếu: "
            + repr(missing_model)
        )


def verify_source():
    source = SURVEYS.read_text(
        encoding="utf-8"
    )
    ast.parse(source)

    fn = get_function(
        source,
        "luu_theo_doi_nam_hoc",
    )

    required = (
        FIX_MARK,
        "study_location_scope: Annotated[str, Form()]",
        "disability_can_learn: Annotated[str, Form()]",
        "disability_access_education: Annotated[str, Form()]",
        "record.study_location_scope = _fix26c_study or None",
        "record.disability_can_learn = _fix26c_can",
        "record.disability_access_education = _fix26c_access",
    )
    missing = [
        x for x in required
        if x not in fn
    ]
    if missing:
        raise RuntimeError(
            "Hàm lưu sau sửa thiếu: "
            + repr(missing)
        )

    checks = {
        "study_location_scope": (
            r'^[ \t]*record\.study_location_scope'
            r'[ \t]*=[ \t]*_fix26c_study or None[ \t]*$'
        ),
        "disability_can_learn": (
            r'^[ \t]*record\.disability_can_learn'
            r'[ \t]*=[ \t]*_fix26c_can[ \t]*$'
        ),
        "disability_access_education": (
            r'^[ \t]*record\.disability_access_education'
            r'[ \t]*=[ \t]*_fix26c_access[ \t]*$'
        ),
    }

    for label, pattern in checks.items():
        matches = re.findall(
            pattern,
            fn,
            flags=re.M,
        )
        if len(matches) != 1:
            raise RuntimeError(
                f"Verify {label}: cần 1 phép gán thật, "
                f"thực tế={len(matches)}."
            )


def clear_cache():
    for cache in APP.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(
                cache,
                ignore_errors=True,
            )


def main():
    EXPORTS.mkdir(
        parents=True,
        exist_ok=True,
    )
    BACKUPS.mkdir(
        parents=True,
        exist_ok=True,
    )

    with OUT.open(
        "w",
        encoding="utf-8-sig",
        newline="\n",
    ) as f:
        log(f, "=" * 150)
        log(
            f,
            "FIX 26C - LƯU DỨT ĐIỂM NƠI HỌC + "
            "2 CHỈ BÁO KHUYẾT TẬT",
        )
        log(
            f,
            "SOURCE ONLY - KHÔNG GHI DATABASE",
        )
        log(f, "=" * 150)

        for p in (
            DB,
            SURVEYS,
            YEAR_TEMPLATE,
            MODEL,
        ):
            if not p.exists():
                raise RuntimeError(
                    f"Không tìm thấy: {p}"
                )

        integrity, fk_count, stats = (
            db_precheck()
        )
        db_sha_before = sha256_file(DB)

        log(f, "DB_SHA_BEFORE =", db_sha_before)
        log(f, "INTEGRITY =", integrity)
        log(f, "FK_COUNT =", fk_count)
        log(
            f,
            "CURRENT_NULL_COUNTS =",
            {
                "year_records_total": stats[0],
                "study_location_blank": stats[1],
                "disabled_can_learn_null": stats[2],
                "disabled_access_null": stats[3],
            },
        )

        verify_ui_model()
        log(
            f,
            "UI_AND_MODEL_FIELDS = PASS",
        )

        source_before = SURVEYS.read_text(
            encoding="utf-8-sig"
        )
        ast.parse(source_before)

        stamp = datetime.now().strftime(
            "%Y%m%d_%H%M%S"
        )
        backup_root = (
            BACKUPS
            / f"source_truoc_FIX26C_{stamp}"
        )
        backup_file = (
            backup_root
            / SURVEYS.relative_to(ROOT)
        )
        backup_file.parent.mkdir(
            parents=True,
            exist_ok=False,
        )
        shutil.copy2(
            SURVEYS,
            backup_file,
        )
        log(
            f,
            "SOURCE_BACKUP =",
            backup_root,
        )

        try:
            source_after, commit_count = (
                patch_source(source_before)
            )
            SURVEYS.write_text(
                source_after,
                encoding="utf-8",
            )

            py_compile.compile(
                str(SURVEYS),
                doraise=True,
            )
            verify_source()
            clear_cache()

            log(
                f,
                "DB_COMMIT_LINES_FOUND =",
                commit_count,
            )
            log(
                f,
                "PY_COMPILE = PASS",
            )
            log(
                f,
                "SAVE_ROUTE_VERIFY = PASS",
            )

        except Exception:
            shutil.copy2(
                backup_file,
                SURVEYS,
            )
            clear_cache()
            log(
                f,
                "ROLLBACK_SOURCE = PASS",
            )
            raise

        db_sha_after = sha256_file(DB)
        if db_sha_after != db_sha_before:
            shutil.copy2(
                backup_file,
                SURVEYS,
            )
            clear_cache()
            raise RuntimeError(
                "DB thay đổi trong lúc cài source; "
                "đã khôi phục source."
            )

        log(
            f,
            "DB_SHA_AFTER =",
            db_sha_after,
        )
        log(
            f,
            "DATABASE_WRITES_THIS_RUN = 0",
        )
        log(
            f,
            "FIX26C_SUCCESS = YES",
        )
        log(f, "")
        log(
            f,
            "SAU CÀI: restart Uvicorn + Ctrl+F5.",
        )
        log(
            f,
            "TEST A: chọn Nơi học -> Lưu -> mở lại; "
            "phải giữ nguyên lựa chọn.",
        )
        log(
            f,
            "TEST B: chọn Có khả năng học tập / "
            "Được tiếp cận giáo dục -> Lưu -> mở lại; "
            "phải giữ nguyên.",
        )
        log(
            f,
            "TEST C: xuất lại MN-02 sau khi lưu.",
        )
        log(
            f,
            "KHÔNG TỰ ĐIỀN DỮ LIỆU CŨ ĐANG NULL.",
        )
        log(f, "=" * 150)

    return 0


if __name__ == "__main__":
    try:
        rc = main()
    except Exception as exc:
        try:
            EXPORTS.mkdir(
                parents=True,
                exist_ok=True,
            )
            with OUT.open(
                "a",
                encoding="utf-8-sig",
                newline="\n",
            ) as f:
                log(f, "")
                log(f, "=" * 150)
                log(
                    f,
                    "FIX26C_SUCCESS = NO",
                )
                log(
                    f,
                    "ERROR =",
                    repr(exc),
                )
                if DB.exists():
                    log(
                        f,
                        "DB_SHA_CURRENT =",
                        sha256_file(DB),
                    )
                log(
                    f,
                    "DỪNG AN TOÀN.",
                )
                log(f, "=" * 150)
        except Exception:
            print(
                "ERROR =",
                repr(exc),
            )
        rc = 1

    raise SystemExit(rc)
