# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
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
YEAR = APP / "templates" / "surveys" / "year_records.html"
EXPORTS = ROOT / "exports"
BACKUPS = ROOT / "backups"
OUT = EXPORTS / "SUA_XUNG_DOT_TU_DONG_TINH_TRANG_HOC_TAP_29C.txt"

MARK_START = "<!-- === BAI29B_SAFE_AUTO_NOT_TRACKED_START === -->"
MARK_END = "<!-- === BAI29B_SAFE_AUTO_NOT_TRACKED_END === -->"

OLD_BIRTH = '    const birthDateRaw = "{{ person.date_of_birth or \'\'} }}";'
NEW_BIRTH = '    const birthDateRaw = "{{ person.date_of_birth or \'\' }}";\n    const savedLearningStatus =\n        "{{ selected_record.learning_status if selected_record and selected_record.learning_status else \'\' }}";'
OLD_GUARD = '        const current = String(select.value || "").trim().toUpperCase();\n\n        if (\n            current\n            && current !== "CHUA_XAC_DINH"\n        ) {\n            return;\n        }\n\n        if (!ensureOption(select)) return;\n\n        select.value = "KHONG_THUOC_DIEN";\n        showNote(select, age);'
NEW_GUARD = '        const current = String(select.value || "").trim().toUpperCase();\n        const saved = String(savedLearningStatus || "").trim().toUpperCase();\n\n        if (\n            saved\n            && saved !== "CHUA_XAC_DINH"\n            && saved !== "KHONG_THUOC_DIEN"\n        ) {\n            return;\n        }\n\n        if (!ensureOption(select)) return;\n\n        if (saved === "KHONG_THUOC_DIEN") {\n            select.value = "KHONG_THUOC_DIEN";\n            return;\n        }\n\n        select.value = "KHONG_THUOC_DIEN";\n        showNote(select, age);'


def log(f, *parts):
    line = " ".join(str(x) for x in parts)
    print(line)
    f.write(line + "\n")
    f.flush()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as src:
        for chunk in iter(lambda: src.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def db_health():
    con = sqlite3.connect(
        f"file:{DB.as_posix()}?mode=ro",
        uri=True,
        timeout=30,
    )
    try:
        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
        fk = con.execute("PRAGMA foreign_key_check").fetchall()
        row79 = con.execute(
            "SELECT p.id, p.full_name, p.date_of_birth, "
            "y.learning_status, y.school_id, y.class_id, "
            "y.school_name_reported, y.class_name_reported "
            "FROM survey_people p "
            "LEFT JOIN survey_person_year_records y "
            "ON y.survey_person_id=p.id AND y.school_year_id=2 "
            "WHERE p.id=79 LIMIT 1"
        ).fetchone()
    finally:
        con.close()

    if integrity != "ok" or fk:
        raise RuntimeError(
            f"DB health không đạt: integrity={integrity}; FK={len(fk)}"
        )
    return integrity, len(fk), row79


def clear_cache():
    for cache in APP.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)


def main():
    EXPORTS.mkdir(parents=True, exist_ok=True)
    BACKUPS.mkdir(parents=True, exist_ok=True)

    with OUT.open("w", encoding="utf-8-sig", newline="\n") as f:
        log(f, "=" * 165)
        log(f, "BÀI 29C - SỬA XUNG ĐỘT TỰ ĐỘNG 'ĐANG HỌC' ↔ 'KHÔNG THUỘC DIỆN THEO DÕI'")
        log(f, "CHỈ SỬA BLOCK BÀI 29B TRONG TEMPLATE - KHÔNG GHI DATABASE")
        log(f, "KHÔNG ĐỤNG BACKEND, XMC, TRÌNH ĐỘ, NƠI HỌC, KHUYẾT TẬT, MN/TH/THCS")
        log(f, "=" * 165)

        for p in (DB, YEAR):
            if not p.exists():
                raise RuntimeError(f"Không tìm thấy: {p}")

        integrity, fk_count, row79 = db_health()
        db_sha_before = sha256_file(DB)

        log(f, "DB_SHA_BEFORE =", db_sha_before)
        log(f, "INTEGRITY =", integrity)
        log(f, "FK_COUNT =", fk_count)
        log(f, "PERSON_79_DB =", row79)

        before = YEAR.read_text(encoding="utf-8-sig")

        if MARK_START not in before or MARK_END not in before:
            raise RuntimeError(
                "Không tìm thấy block Bài 29B. Dừng để không sửa nhầm."
            )

        start = before.index(MARK_START)
        end = before.index(MARK_END, start) + len(MARK_END)
        block = before[start:end]

        if "const savedLearningStatus =" in block:
            log(f, "STATUS = 29C_ALREADY_INSTALLED")
            log(f, "DATABASE_WRITES_THIS_RUN = 0")
            log(f, "DB_SHA_AFTER =", sha256_file(DB))
            log(f, "BAI29C_SUCCESS = YES")
            return 0

        birth_count = block.count(OLD_BIRTH)
        guard_count = block.count(OLD_GUARD)

        log(f, "BIRTH_PATCH_POINT_COUNT =", birth_count)
        log(f, "GUARD_PATCH_POINT_COUNT =", guard_count)

        if birth_count != 1:
            raise RuntimeError(
                f"Không tìm thấy đúng 1 điểm chèn savedLearningStatus; count={birth_count}"
            )

        if guard_count != 1:
            raise RuntimeError(
                f"Không tìm thấy đúng 1 guard Bài 29B cần sửa; count={guard_count}"
            )

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_root = BACKUPS / f"source_truoc_BAI29C_{stamp}"
        backup_file = backup_root / YEAR.relative_to(ROOT)
        backup_file.parent.mkdir(parents=True, exist_ok=False)
        shutil.copy2(YEAR, backup_file)
        log(f, "SOURCE_BACKUP =", backup_root)

        try:
            new_block = block.replace(OLD_BIRTH, NEW_BIRTH, 1)
            new_block = new_block.replace(OLD_GUARD, NEW_GUARD, 1)
            after = before[:start] + new_block + before[end:]

            if 'name="learning_status"' not in after:
                raise RuntimeError("Mất control learning_status.")
            if 'name="is_literacy_target"' not in after:
                raise RuntimeError("Mất control XMC.")
            if 'name="disability_status"' not in after:
                raise RuntimeError("Mất control khuyết tật.")
            if 'name="study_location_scope"' not in after:
                raise RuntimeError("Mất control Nơi học.")

            YEAR.write_text(after, encoding="utf-8")
            clear_cache()

            check = YEAR.read_text(encoding="utf-8")
            if "const savedLearningStatus =" not in check:
                raise RuntimeError("Không thấy savedLearningStatus sau khi ghi.")
            if 'saved !== "CHUA_XAC_DINH"' not in check:
                raise RuntimeError("Guard mới chưa được ghi đúng.")

            log(f, "PATCH_SCOPE = ONLY_BAI29B_BLOCK")
            log(f, "BACKEND_CHANGE = NONE")
            log(f, "SOURCE_VERIFY = PASS")

        except Exception:
            shutil.copy2(backup_file, YEAR)
            clear_cache()
            log(f, "ROLLBACK_SOURCE = PASS")
            raise

        db_sha_after = sha256_file(DB)
        if db_sha_after != db_sha_before:
            shutil.copy2(backup_file, YEAR)
            clear_cache()
            raise RuntimeError(
                "DB thay đổi trong lúc cài source; đã rollback template."
            )

        log(f, "DB_SHA_AFTER =", db_sha_after)
        log(f, "DATABASE_WRITES_THIS_RUN = 0")
        log(f, "BAI29C_SUCCESS = YES")
        log(f, "")
        log(f, "LOGIC:")
        log(f, " - Nếu DB đã lưu trạng thái cụ thể: KHÔNG ghi đè.")
        log(f, " - Nếu DB trống/CHUA_XAC_DINH, tuổi >18, không có trường/lớp:")
        log(f, "   cho phép sửa giá trị ĐANG HỌC do script cũ tự suy ra trên giao diện")
        log(f, "   thành KHÔNG THUỘC DIỆN THEO DÕI.")
        log(f, " - Người dùng vẫn bấm Lưu theo luồng cũ; script này không tự POST.")
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
                log(f, "BAI29C_SUCCESS = NO")
                log(f, "ERROR =", repr(exc))
                if DB.exists():
                    log(f, "DB_SHA_CURRENT =", sha256_file(DB))
                log(f, "DỪNG AN TOÀN.")
                log(f, "=" * 165)
        except Exception:
            print("ERROR =", repr(exc))
        rc = 1

    raise SystemExit(rc)
