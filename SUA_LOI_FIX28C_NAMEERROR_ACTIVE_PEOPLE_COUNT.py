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
YEAR = APP / "templates" / "surveys" / "year_records.html"

BACKUPS = ROOT / "backups"
EXPORTS = ROOT / "exports"
REPORT = EXPORTS / "SUA_LOI_FIX28C_NAMEERROR_ACTIVE_PEOPLE_COUNT.txt"

START_MARK = "# === FIX28C_HEAD_AND_COMPLETION_PREFILL_PREFILL_START ==="
END_MARK = "# === FIX28C_HEAD_AND_COMPLETION_PREFILL_PREFILL_END ==="

BAD_LINE = "        active_people_count > 0\n"
GOOD_LINE = "        len(people) > 0\n"


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


def db_check():
    con = sqlite3.connect(
        f"file:{DB.as_posix()}?mode=ro",
        uri=True,
        timeout=30,
    )
    try:
        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
        fk = con.execute("PRAGMA foreign_key_check").fetchall()
    finally:
        con.close()

    if integrity != "ok" or fk:
        raise RuntimeError(
            f"Database không an toàn: integrity={integrity}; FK={len(fk)}"
        )
    return integrity, len(fk)


def clear_cache():
    for cache in APP.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)


def verify(source: str):
    ast.parse(source)

    if START_MARK not in source or END_MARK not in source:
        raise RuntimeError("Không tìm thấy đúng khối FIX28C cần sửa.")

    start = source.index(START_MARK)
    end = source.index(END_MARK, start) + len(END_MARK)
    block = source[start:end]

    if "active_people_count > 0" in block:
        raise RuntimeError("Sau sửa vẫn còn active_people_count trong khối FIX28C.")

    if "len(people) > 0" not in block:
        raise RuntimeError("Sau sửa chưa có len(people) > 0 trong khối FIX28C.")

    if '"fix28c_ready_to_complete": fix28c_ready_to_complete' not in source:
        raise RuntimeError("Context FIX28C không còn đúng.")

    if "BAI_13B_12_V2_3_9_AUTO_FINISH_HOUSEHOLD_START" not in source:
        raise RuntimeError("Mất backend tự hoàn thành hộ hiện có.")

    if "finish_household" not in source:
        raise RuntimeError("Mất tham số finish_household.")


def verify_jinja():
    from jinja2 import Environment, FileSystemLoader

    env = Environment(loader=FileSystemLoader(str(APP / "templates")))
    env.get_template("surveys/quick_entry.html")
    env.get_template("surveys/year_records.html")


def main():
    EXPORTS.mkdir(parents=True, exist_ok=True)
    BACKUPS.mkdir(parents=True, exist_ok=True)

    with REPORT.open("w", encoding="utf-8-sig", newline="\n") as f:
        log(f, "=" * 150)
        log(f, "SỬA LỖI FIX28C - NameError active_people_count")
        log(f, "CHỈ SỬA SOURCE - KHÔNG GHI DATABASE")
        log(f, "=" * 150)

        for p in (DB, SURVEYS, QUICK, YEAR):
            if not p.exists():
                raise RuntimeError(f"Không tìm thấy: {p}")

        integrity, fk_count = db_check()
        db_sha_before = sha256_file(DB)

        log(f, "DB_SHA_BEFORE =", db_sha_before)
        log(f, "INTEGRITY =", integrity)
        log(f, "FK_COUNT =", fk_count)

        before = SURVEYS.read_text(encoding="utf-8-sig")

        if START_MARK not in before or END_MARK not in before:
            raise RuntimeError(
                "Source hiện tại không có khối FIX28C; dừng để tránh sửa nhầm."
            )

        start = before.index(START_MARK)
        end = before.index(END_MARK, start) + len(END_MARK)
        block = before[start:end]

        bad_count = block.count("active_people_count > 0")
        good_count = block.count("len(people) > 0")

        log(f, "BAD_COUNT_IN_FIX28C_BLOCK =", bad_count)
        log(f, "GOOD_COUNT_IN_FIX28C_BLOCK =", good_count)

        if bad_count == 0 and good_count == 1:
            log(f, "SOURCE_STATUS = ALREADY_FIXED")
            verify(before)
            py_compile.compile(str(SURVEYS), doraise=True)
            verify_jinja()
            clear_cache()
            log(f, "PY_COMPILE = PASS")
            log(f, "JINJA_VERIFY = PASS")
            log(f, "DATABASE_WRITES_THIS_RUN = 0")
            log(f, "DB_SHA_AFTER =", sha256_file(DB))
            log(f, "HOTFIX_SUCCESS = YES")
            return 0

        if bad_count != 1:
            raise RuntimeError(
                f"Cần đúng 1 lỗi active_people_count trong khối FIX28C; thực tế={bad_count}."
            )

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_root = BACKUPS / f"source_truoc_FIX28C_NAMEERROR_{stamp}"
        backup_file = backup_root / SURVEYS.relative_to(ROOT)
        backup_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(SURVEYS, backup_file)

        log(f, "SOURCE_BACKUP =", backup_root)

        try:
            new_block = block.replace(
                "active_people_count > 0",
                "len(people) > 0",
                1,
            )
            after = before[:start] + new_block + before[end:]

            SURVEYS.write_text(after, encoding="utf-8")

            py_compile.compile(str(SURVEYS), doraise=True)
            current = SURVEYS.read_text(encoding="utf-8")
            verify(current)
            verify_jinja()
            clear_cache()

            log(f, "PATCH = active_people_count > 0  ->  len(people) > 0")
            log(f, "PY_COMPILE = PASS")
            log(f, "JINJA_VERIFY = PASS")

        except Exception:
            shutil.copy2(backup_file, SURVEYS)
            clear_cache()
            log(f, "ROLLBACK_SOURCE = PASS")
            raise

        db_sha_after = sha256_file(DB)
        if db_sha_after != db_sha_before:
            shutil.copy2(backup_file, SURVEYS)
            clear_cache()
            raise RuntimeError(
                "Database thay đổi trong lúc sửa source; source đã rollback."
            )

        log(f, "DB_SHA_AFTER =", db_sha_after)
        log(f, "DATABASE_WRITES_THIS_RUN = 0")
        log(f, "HOTFIX_SUCCESS = YES")
        log(f, "=" * 150)

    return 0


if __name__ == "__main__":
    try:
        rc = main()
    except Exception as exc:
        try:
            EXPORTS.mkdir(parents=True, exist_ok=True)
            with REPORT.open("a", encoding="utf-8-sig", newline="\n") as f:
                log(f, "")
                log(f, "=" * 150)
                log(f, "HOTFIX_SUCCESS = NO")
                log(f, "ERROR =", repr(exc))
                if DB.exists():
                    log(f, "DB_SHA_CURRENT =", sha256_file(DB))
                log(f, "DỪNG AN TOÀN.")
                log(f, "=" * 150)
        except Exception:
            print("ERROR =", repr(exc))
        rc = 1

    raise SystemExit(rc)
