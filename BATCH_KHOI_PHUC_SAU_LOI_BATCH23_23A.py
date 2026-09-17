# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import py_compile
import shutil
import sqlite3
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(r"C:\PhoCap")
DB = ROOT / "data" / "phocap.db"
BACKUP_DIR = ROOT / "backups"
EXPORT_DIR = ROOT / "exports"

MAIN = ROOT / "app" / "main.py"
MENU = ROOT / "app" / "templates" / "partials" / "dropdown_menu_v1.html"
ROUTER = ROOT / "app" / "routers" / "survey_cleanup_safe.py"
TEMPLATE = ROOT / "app" / "templates" / "data_tools" / "survey_cleanup.html"

OUT = EXPORT_DIR / "BATCH_KHOI_PHUC_SAU_LOI_BATCH23_23A.txt"

EXPECTED_DB_SHA = "2a43e36ff8f192abb46668faa1366ed7242984bfd876f90572cd83b90ee7837e"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def log(f, *parts):
    s = " ".join(str(x) for x in parts)
    print(s)
    f.write(s + "\n")
    f.flush()


def db_health():
    sha = sha256_file(DB)
    con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True, timeout=30)
    try:
        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
        fk = con.execute("PRAGMA foreign_key_check").fetchall()
    finally:
        con.close()
    return sha, integrity, len(fk)


def find_latest_backup() -> Path:
    candidates = sorted(
        [p for p in BACKUP_DIR.glob("source_truoc_BATCH23_*") if p.is_dir()],
        key=lambda p: p.name,
        reverse=True,
    )
    if not candidates:
        raise RuntimeError(
            "Không tìm thấy thư mục backup source_truoc_BATCH23_*."
        )
    return candidates[0]


def restore_from_backup(backup_root: Path, target: Path) -> bool:
    rel = target.relative_to(ROOT)
    src = backup_root / rel
    if src.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)
        return True
    return False


def main():
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    with OUT.open("w", encoding="utf-8-sig", newline="\n") as f:
        log(f, "=" * 160)
        log(f, "BATCH 23A - KHÔI PHỤC SOURCE TRƯỚC BATCH 23 SAU LỖI INTERNAL SERVER ERROR")
        log(f, "KHÔNG GHI DATABASE")
        log(f, "=" * 160)

        sha, integrity, fk_count = db_health()
        log(f, "DB_SHA =", sha)
        log(f, "EXPECTED_DB_SHA =", EXPECTED_DB_SHA)
        log(f, "INTEGRITY =", integrity)
        log(f, "FK =", fk_count)

        if sha != EXPECTED_DB_SHA:
            raise RuntimeError("DB SHA đã thay đổi; dừng để không khôi phục source mù.")
        if integrity != "ok" or fk_count != 0:
            raise RuntimeError("Database health không đạt.")

        backup_root = find_latest_backup()
        log(f, "SOURCE_BACKUP_USED =", backup_root)

        restored_main = restore_from_backup(backup_root, MAIN)
        restored_menu = restore_from_backup(backup_root, MENU)

        if not restored_main:
            raise RuntimeError("Backup Batch23 không có app/main.py.")
        if not restored_menu:
            raise RuntimeError("Backup Batch23 không có dropdown_menu_v1.html.")

        router_backup = backup_root / ROUTER.relative_to(ROOT)
        if router_backup.exists():
            shutil.copy2(router_backup, ROUTER)
            router_action = "RESTORED"
        else:
            if ROUTER.exists():
                ROUTER.unlink()
            router_action = "REMOVED_NEW_FILE"

        template_backup = backup_root / TEMPLATE.relative_to(ROOT)
        if template_backup.exists():
            TEMPLATE.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(template_backup, TEMPLATE)
            template_action = "RESTORED"
        else:
            if TEMPLATE.exists():
                TEMPLATE.unlink()
            template_action = "REMOVED_NEW_FILE"

        py_compile.compile(str(MAIN), doraise=True)
        log(f, "PY_COMPILE_MAIN = PASS")

        log(f, "MAIN_RESTORED =", restored_main)
        log(f, "MENU_RESTORED =", restored_menu)
        log(f, "ROUTER_ACTION =", router_action)
        log(f, "TEMPLATE_ACTION =", template_action)

        sha_after, integrity_after, fk_after = db_health()
        log(f, "DB_SHA_AFTER =", sha_after)
        log(f, "INTEGRITY_AFTER =", integrity_after)
        log(f, "FK_AFTER =", fk_after)
        log(f, "DATABASE_WRITES_THIS_RUN = 0")
        log(f, "BATCH_23A_SUCCESS = YES")
        log(f, "NEXT = Khởi động lại Uvicorn và kiểm tra lại http://127.0.0.1:8000")
        log(f, "=" * 160)

    return 0


if __name__ == "__main__":
    try:
        rc = main()
    except Exception as exc:
        try:
            EXPORT_DIR.mkdir(parents=True, exist_ok=True)
            with OUT.open("a", encoding="utf-8-sig", newline="\n") as f:
                log(f, "")
                log(f, "=" * 160)
                log(f, "BATCH_23A_SUCCESS = NO")
                log(f, "ERROR =", repr(exc))
                if DB.exists():
                    log(f, "DB_SHA_CURRENT =", sha256_file(DB))
                log(f, "DỪNG AN TOÀN.")
                log(f, "=" * 160)
        except Exception:
            print("ERROR =", repr(exc))
        rc = 1
    sys.exit(rc)
