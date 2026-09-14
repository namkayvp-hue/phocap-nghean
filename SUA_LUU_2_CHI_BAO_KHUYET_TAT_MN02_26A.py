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
OUT = EXPORTS / "SUA_LUU_2_CHI_BAO_KHUYET_TAT_MN02_26A.txt"

EXPECTED_DB_SHA = "cb821b5500b239756ff4b745b8f36abfaa8a44b9f43de00c26a64cd9db81ce26"

FIX_START = "# === FIX26A_SAVE_DISABILITY_REPORT_FLAGS_START ==="
FIX_END = "# === FIX26A_SAVE_DISABILITY_REPORT_FLAGS_END ==="


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
    sha = sha256_file(DB)
    if sha != EXPECTED_DB_SHA:
        raise RuntimeError(
            "DB SHA đã thay đổi so với lần lỗi FIX26. "
            "Dừng để không sửa source trên nền khác."
        )

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
        stats = con.execute(
            """
            SELECT
                COUNT(*),
                SUM(CASE WHEN disability_can_learn IS NULL THEN 1 ELSE 0 END),
                SUM(CASE WHEN disability_access_education IS NULL THEN 1 ELSE 0 END),
                SUM(CASE WHEN disability_can_learn = 1 THEN 1 ELSE 0 END),
                SUM(CASE WHEN disability_access_education = 1 THEN 1 ELSE 0 END)
            FROM survey_person_year_records
            WHERE disability_status='CO_KHUYET_TAT'
            """
        ).fetchone()
    finally:
        con.close()

    required = {
        "disability_status",
        "disability_can_learn",
        "disability_access_education",
    }
    missing = sorted(required - cols)
    if missing:
        raise RuntimeError("DB thiếu cột: " + ", ".join(missing))

    if integrity != "ok" or fk:
        raise RuntimeError(
            f"DB health không đạt: integrity={integrity}, FK={len(fk)}"
        )

    return sha, tuple(int(x or 0) for x in stats)


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
        raise RuntimeError(f"Không xác định được cuối hàm {name}.")
    return offsets[node.lineno - 1], offsets[node.end_lineno]


def get_function(text: str, name: str) -> str:
    a, b = function_span(text, name)
    return text[a:b]


def replace_function(text: str, name: str, fn: str) -> str:
    a, b = function_span(text, name)
    return text[:a] + fn.rstrip() + "\n\n" + text[b:]


def remove_fix26_blocks(fn: str) -> str:
    # Xóa block FIX26/FIX26A cũ nếu có để cài lại idempotent.
    patterns = [
        re.compile(
            r'^[ \t]*# === FIX26_SAVE_DISABILITY_REPORT_FLAGS_START ===\n'
            r'.*?'
            r'^[ \t]*# === FIX26_SAVE_DISABILITY_REPORT_FLAGS_END ===\n',
            re.M | re.S,
        ),
        re.compile(
            r'^[ \t]*# === FIX26A_SAVE_DISABILITY_REPORT_FLAGS_START ===\n'
            r'.*?'
            r'^[ \t]*# === FIX26A_SAVE_DISABILITY_REPORT_FLAGS_END ===\n',
            re.M | re.S,
        ),
    ]
    for p in patterns:
        fn = p.sub("", fn)
    return fn


def ensure_form_params(fn: str) -> str:
    has_can = "disability_can_learn: Annotated[str, Form()]" in fn
    has_access = "disability_access_education: Annotated[str, Form()]" in fn
    if has_can and has_access:
        return fn

    m = re.search(
        r'^(?P<i>[ \t]*)disability_status:\s*Annotated\[str,\s*Form\(\)\]'
        r'.*?\n',
        fn,
        re.M,
    )
    if not m:
        raise RuntimeError(
            "Không tìm thấy tham số disability_status để thêm 2 trường form."
        )

    indent = m.group("i")
    extra = ""
    if not has_can:
        extra += (
            f'{indent}disability_can_learn: '
            'Annotated[str, Form()] = "",\n'
        )
    if not has_access:
        extra += (
            f'{indent}disability_access_education: '
            'Annotated[str, Form()] = "",\n'
        )

    return fn[:m.end()] + extra + fn[m.end():]


def ensure_values(fn: str) -> str:
    """
    Nếu nền hiện tại đã có disability_*_value thì giữ nguyên.
    Nếu chưa có thì tự parse trực tiếp từ Form bằng hàm Có/Không hiện có.
    """
    has_can = "disability_can_learn_value" in fn
    has_access = "disability_access_education_value" in fn
    if has_can and has_access:
        return fn

    m = re.search(
        r'^(?P<i>[ \t]*)if disability_status not in DISABILITY_STATUS_LABELS:\n',
        fn,
        re.M,
    )
    if not m:
        raise RuntimeError(
            "Không tìm thấy kiểm tra disability_status."
        )

    i = m.group("i")
    block = (
        f"{i}{FIX_START}\n"
        f"{i}disability_can_learn_value, _fix26a_err_can = "
        "chuyen_gia_tri_co_khong(\n"
        f"{i}    disability_can_learn,\n"
        f'{i}    "Có khả năng học tập",\n'
        f"{i})\n"
        f"{i}disability_access_education_value, _fix26a_err_access = "
        "chuyen_gia_tri_co_khong(\n"
        f"{i}    disability_access_education,\n"
        f'{i}    "Được tiếp cận giáo dục",\n'
        f"{i})\n"
        f"{i}for _fix26a_error in (_fix26a_err_can, _fix26a_err_access):\n"
        f"{i}    if _fix26a_error:\n"
        f"{i}        errors.append(_fix26a_error)\n"
        f"{i}if disability_status != \"CO_KHUYET_TAT\":\n"
        f"{i}    disability_can_learn_value = None\n"
        f"{i}    disability_access_education_value = None\n"
        f"{i}{FIX_END}\n\n"
    )
    return fn[:m.start()] + block + fn[m.start():]


def remove_old_assignments(fn: str) -> str:
    # Xóa mọi phép gán cũ của đúng 2 trường để tránh block cũ ghi đè.
    pats = (
        r'^[ \t]*form_record\.disability_can_learn\s*=.*?\n',
        r'^[ \t]*form_record\.disability_access_education\s*=.*?\n',
        r'^[ \t]*record\.disability_can_learn\s*=.*?\n',
        r'^[ \t]*record\.disability_access_education\s*=.*?\n',
    )
    for pat in pats:
        fn = re.sub(pat, "", fn, flags=re.M)
    return fn


def insert_error_branch_assignments(fn: str) -> str:
    error_pos = fn.find("    if errors:")
    if error_pos < 0:
        raise RuntimeError("Không tìm thấy nhánh if errors.")

    return_pos = fn.find(
        "        return templates.TemplateResponse(",
        error_pos,
    )
    if return_pos < 0:
        raise RuntimeError(
            "Không tìm thấy TemplateResponse trong nhánh validation."
        )

    block = (
        "        form_record.disability_can_learn = "
        "disability_can_learn_value\n"
        "        form_record.disability_access_education = "
        "disability_access_education_value\n\n"
    )
    return fn[:return_pos] + block + fn[return_pos:]


def insert_before_commit(fn: str) -> tuple[str, int]:
    """
    FIX26 cũ thất bại vì giả định try/db.commit đứng liền nhau.
    Bản này không giả định cấu trúc try.
    Nó tìm lệnh db.commit() thật trong hàm và gán 2 giá trị
    NGAY TRƯỚC commit, cùng indentation với db.commit().
    """
    matches = list(re.finditer(
        r'^(?P<i>[ \t]*)db\.commit\(\)\s*$',
        fn,
        flags=re.M,
    ))
    if not matches:
        raise RuntimeError(
            "Không tìm thấy bất kỳ dòng db.commit() nào trong hàm lưu năm học."
        )

    # Ưu tiên commit cuối cùng của hàm: đây là commit lưu bản ghi năm học.
    m = matches[-1]
    i = m.group("i")
    block = (
        f"{i}# === FIX26A_FINAL_ASSIGN_BEFORE_COMMIT ===\n"
        f"{i}record.disability_can_learn = disability_can_learn_value\n"
        f"{i}record.disability_access_education = "
        "disability_access_education_value\n"
    )
    return fn[:m.start()] + block + fn[m.start():], len(matches)


def patch_source(source: str) -> tuple[str, int]:
    fn = get_function(source, "luu_theo_doi_nam_hoc")
    fn = remove_fix26_blocks(fn)
    fn = ensure_form_params(fn)
    fn = ensure_values(fn)
    fn = remove_old_assignments(fn)
    fn = insert_error_branch_assignments(fn)
    fn, commit_count = insert_before_commit(fn)
    return replace_function(
        source,
        "luu_theo_doi_nam_hoc",
        fn,
    ), commit_count


def verify_static():
    template = YEAR_TEMPLATE.read_text(encoding="utf-8-sig")
    model = MODEL.read_text(encoding="utf-8-sig")

    for needle in (
        'name="disability_can_learn"',
        'name="disability_access_education"',
    ):
        if needle not in template:
            raise RuntimeError(
                f"Giao diện thiếu field: {needle}"
            )

    for needle in (
        "disability_can_learn",
        "disability_access_education",
    ):
        if needle not in model:
            raise RuntimeError(
                f"Model thiếu field: {needle}"
            )


def verify_source():
    source = SURVEYS.read_text(encoding="utf-8")
    ast.parse(source)
    fn = get_function(source, "luu_theo_doi_nam_hoc")

    must = (
        "disability_can_learn: Annotated[str, Form()]",
        "disability_access_education: Annotated[str, Form()]",
        "form_record.disability_can_learn = disability_can_learn_value",
        "form_record.disability_access_education = disability_access_education_value",
        "record.disability_can_learn = disability_can_learn_value",
        "record.disability_access_education = disability_access_education_value",
        "FIX26A_FINAL_ASSIGN_BEFORE_COMMIT",
    )
    missing = [x for x in must if x not in fn]
    if missing:
        raise RuntimeError(
            "Verify hàm lưu còn thiếu: " + repr(missing)
        )

    # Gán record thật phải đúng một lần.
    if fn.count(
        "record.disability_can_learn = disability_can_learn_value"
    ) != 1:
        raise RuntimeError(
            "Gán disability_can_learn vào record không đúng 1 lần."
        )
    if fn.count(
        "record.disability_access_education = "
        "disability_access_education_value"
    ) != 1:
        raise RuntimeError(
            "Gán disability_access_education vào record không đúng 1 lần."
        )


def clear_cache():
    for p in APP.rglob("__pycache__"):
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)


def main():
    EXPORTS.mkdir(parents=True, exist_ok=True)
    BACKUPS.mkdir(parents=True, exist_ok=True)

    with OUT.open("w", encoding="utf-8-sig", newline="\n") as f:
        log(f, "=" * 150)
        log(f, "FIX 26A - SỬA LƯU 2 CHỈ BÁO KHUYẾT TẬT PHỤC VỤ MN-02")
        log(f, "BẢN SỬA SAU LỖI: KHÔNG CÒN GIẢ ĐỊNH try/db.commit() LIỀN NHAU")
        log(f, "SOURCE ONLY - KHÔNG GHI DATABASE")
        log(f, "=" * 150)

        for p in (DB, SURVEYS, YEAR_TEMPLATE, MODEL):
            if not p.exists():
                raise RuntimeError(f"Không tìm thấy: {p}")

        db_sha, stats = db_precheck()
        log(f, "DB_SHA =", db_sha)
        log(
            f,
            "DISABLED_ROWS_CURRENT =",
            {
                "total": stats[0],
                "can_learn_null": stats[1],
                "access_education_null": stats[2],
                "can_learn_yes": stats[3],
                "access_education_yes": stats[4],
            },
        )

        verify_static()
        log(f, "UI_AND_MODEL_FIELDS = PASS")

        source_before = SURVEYS.read_text(encoding="utf-8-sig")
        py_compile.compile(str(SURVEYS), doraise=True)

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_root = BACKUPS / f"source_truoc_FIX26A_{stamp}"
        backup_file = backup_root / SURVEYS.relative_to(ROOT)
        backup_file.parent.mkdir(parents=True, exist_ok=False)
        shutil.copy2(SURVEYS, backup_file)
        log(f, "SOURCE_BACKUP =", backup_root)

        try:
            source_after, commit_count = patch_source(source_before)
            SURVEYS.write_text(source_after, encoding="utf-8")

            py_compile.compile(str(SURVEYS), doraise=True)
            verify_source()
            clear_cache()

            log(f, "DB_COMMIT_LINES_FOUND_IN_FUNCTION =", commit_count)
            log(f, "PY_COMPILE = PASS")
            log(f, "SAVE_ROUTE_VERIFY = PASS")

        except Exception:
            shutil.copy2(backup_file, SURVEYS)
            clear_cache()
            log(f, "ROLLBACK_SOURCE = PASS")
            raise

        if sha256_file(DB) != db_sha:
            shutil.copy2(backup_file, SURVEYS)
            clear_cache()
            raise RuntimeError(
                "DB thay đổi trong lúc cài source; đã khôi phục source."
            )

        log(f, "DB_SHA_AFTER =", sha256_file(DB))
        log(f, "DATABASE_WRITES_THIS_RUN = 0")
        log(f, "FIX26A_SUCCESS = YES")
        log(f, "")
        log(f, "KIỂM TRA SAU CÀI:")
        log(f, "1. Khởi động lại Uvicorn và Ctrl+F5.")
        log(f, "2. Mở đúng trẻ đang 'Có khuyết tật'.")
        log(f, "3. Chọn 'Có khả năng học tập' = Có.")
        log(f, "4. Chọn 'Được tiếp cận giáo dục' = Có.")
        log(f, "5. Bấm Lưu, sau đó mở lại đúng hồ sơ.")
        log(f, "6. Hai ô phải vẫn giữ 'Có'.")
        log(f, "7. Xuất lại MN-02 để kiểm tra cột Số lượng/Tiếp cận GD/Tỉ lệ.")
        log(f, "")
        log(f, "KHÔNG_TU_DONG_SUA_DU_LIEU_CU_NULL = YES")
        log(f, "=" * 150)

    return 0


if __name__ == "__main__":
    try:
        rc = main()
    except Exception as exc:
        try:
            EXPORTS.mkdir(parents=True, exist_ok=True)
            with OUT.open("a", encoding="utf-8-sig", newline="\n") as f:
                log(f, "")
                log(f, "=" * 150)
                log(f, "FIX26A_SUCCESS = NO")
                log(f, "ERROR =", repr(exc))
                if DB.exists():
                    log(f, "DB_SHA_CURRENT =", sha256_file(DB))
                log(f, "DỪNG AN TOÀN.")
                log(f, "=" * 150)
        except Exception:
            print("ERROR =", repr(exc))
        rc = 1

    sys.exit(rc)
