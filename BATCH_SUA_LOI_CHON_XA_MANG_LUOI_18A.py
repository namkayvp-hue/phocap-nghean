# -*- coding: utf-8 -*-
from __future__ import annotations

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
DB = ROOT / "data" / "phocap.db"
ROUTER = ROOT / "app" / "routers" / "network_current.py"
BACKUP_DIR = ROOT / "backups"
EXPORT_DIR = ROOT / "exports"
OUT = EXPORT_DIR / "BATCH_SUA_LOI_CHON_XA_MANG_LUOI_18A.txt"

EXPECTED_DB_SHA = "2a43e36ff8f192abb46668faa1366ed7242984bfd876f90572cd83b90ee7837e"

OLD_SIGNATURE = '''def network_current_page(
    request: Request,
    commune_id: int | None = None,
    school_id: int | None = None,
    level: str | None = None,
    status: str | None = None,
):'''

NEW_SIGNATURE = '''def network_current_page(
    request: Request,
    commune_id: str | None = None,
    school_id: str | None = None,
    level: str | None = None,
    status: str | None = None,
):'''

OLD_ACTOR_BLOCK = '''    actor = _actor(request)
    if actor is None or actor["scope"] == "DENY":
        return RedirectResponse(url="/", status_code=303)

    with _conn() as con:
        communes = _communes(con, actor)
        schools = _schools_for_actor(con, actor, commune_id)

        selected_school = None
        if school_id is not None and _school_allowed(con, actor, int(school_id)):
            selected_school = next((x for x in schools if int(x["id"]) == int(school_id)), None)

        if actor["scope"] == "SCHOOL" and actor.get("school_id"):
            sid = int(actor["school_id"])
            if _school_allowed(con, actor, sid):
                selected_school = next((x for x in schools if int(x["id"]) == sid), None)
                school_id = sid

        levels = _levels_for_school(con, int(school_id)) if selected_school else []
'''

NEW_ACTOR_BLOCK = '''    actor = _actor(request)
    if actor is None or actor["scope"] == "DENY":
        return RedirectResponse(url="/", status_code=303)

    def _optional_positive_int(value):
        text = str(value or "").strip()
        if not text:
            return None
        try:
            number = int(text)
        except Exception:
            return None
        return number if number > 0 else None

    commune_id_int = _optional_positive_int(commune_id)
    school_id_int = _optional_positive_int(school_id)

    with _conn() as con:
        communes = _communes(con, actor)
        schools = _schools_for_actor(con, actor, commune_id_int)

        selected_school = None
        if school_id_int is not None and _school_allowed(con, actor, school_id_int):
            selected_school = next((x for x in schools if int(x["id"]) == school_id_int), None)

        if actor["scope"] == "SCHOOL" and actor.get("school_id"):
            sid = int(actor["school_id"])
            if _school_allowed(con, actor, sid):
                selected_school = next((x for x in schools if int(x["id"]) == sid), None)
                school_id_int = sid

        levels = _levels_for_school(con, school_id_int) if selected_school and school_id_int is not None else []
'''

OLD_CONTEXT = '''                "selected_commune_id": commune_id,
                "selected_school": selected_school,
                "selected_school_id": int(school_id) if school_id else None,
'''

NEW_CONTEXT = '''                "selected_commune_id": commune_id_int,
                "selected_school": selected_school,
                "selected_school_id": school_id_int,
'''

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()

def log(f, *parts):
    s = " ".join(str(x) for x in parts)
    print(s)
    f.write(s + "\n")
    f.flush()

def main():
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    with OUT.open("w", encoding="utf-8-sig", newline="\n") as f:
        log(f, "=" * 140)
        log(f, "BATCH 18A - SỬA LỖI CHỌN XÃ/PHƯỜNG Ở MẠNG LƯỚI HIỆN HÀNH")
        log(f, "Lỗi: GET form gửi school_id='' nên FastAPI parse int trước khi vào route và trả 422.")
        log(f, "Chỉ sửa source router; KHÔNG ghi dữ liệu nghiệp vụ.")
        log(f, "=" * 140)

        db_sha = sha256_file(DB)
        log(f, "DB_SHA_BEFORE =", db_sha)
        log(f, "EXPECTED_DB_SHA =", EXPECTED_DB_SHA)
        if db_sha != EXPECTED_DB_SHA:
            raise RuntimeError("DB SHA khác nền Batch 18.")

        con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True, timeout=30)
        try:
            integ = con.execute("PRAGMA integrity_check").fetchone()[0]
            fk = con.execute("PRAGMA foreign_key_check").fetchall()
        finally:
            con.close()

        log(f, "INTEGRITY =", integ)
        log(f, "FK =", len(fk))
        if integ != "ok" or fk:
            raise RuntimeError("Database health không đạt.")

        if not ROUTER.exists():
            raise RuntimeError("Không tìm thấy app\\routers\\network_current.py")

        before = ROUTER.read_text(encoding="utf-8")
        before_sha = sha256_file(ROUTER)
        log(f, "ROUTER_SHA_BEFORE =", before_sha)

        already = (
            "commune_id: str | None = None" in before
            and "school_id: str | None = None" in before
            and "commune_id_int = _optional_positive_int(commune_id)" in before
        )

        if already:
            log(f, "PATCH_STATUS = ALREADY_FIXED")
            py_compile.compile(str(ROUTER), doraise=True)
            log(f, "PY_COMPILE = PASS")
        else:
            for needle in (OLD_SIGNATURE, OLD_ACTOR_BLOCK, OLD_CONTEXT):
                if needle not in before:
                    raise RuntimeError(
                        "Router không đúng nền Batch 18 đã khóa; dừng để không sửa nhầm source."
                    )

            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = BACKUP_DIR / f"network_current_truoc_18A_{ts}.py"
            shutil.copy2(ROUTER, backup_path)
            log(f, "SOURCE_BACKUP =", backup_path)

            after = before.replace(OLD_SIGNATURE, NEW_SIGNATURE, 1)
            after = after.replace(OLD_ACTOR_BLOCK, NEW_ACTOR_BLOCK, 1)
            after = after.replace(OLD_CONTEXT, NEW_CONTEXT, 1)

            ROUTER.write_text(after, encoding="utf-8")

            try:
                py_compile.compile(str(ROUTER), doraise=True)
                log(f, "PY_COMPILE = PASS")
            except Exception:
                shutil.copy2(backup_path, ROUTER)
                log(f, "ROLLBACK_SOURCE = PASS")
                raise

            log(f, "PATCH_STATUS = COMMIT_SOURCE")

        log(f, "ROUTER_SHA_AFTER =", sha256_file(ROUTER))
        log(f, "DB_SHA_AFTER =", sha256_file(DB))
        log(f, "DATABASE_WRITES_THIS_RUN = 0")
        log(f, "BATCH_18A_SUCCESS = YES")
        log(f, "TEST = Khởi động lại Uvicorn rồi mở http://127.0.0.1:8000/mang-luoi-hien-hanh")
        log(f, "=" * 140)
    return 0

if __name__ == "__main__":
    try:
        rc = main()
    except Exception as exc:
        try:
            EXPORT_DIR.mkdir(parents=True, exist_ok=True)
            with OUT.open("a", encoding="utf-8-sig", newline="\n") as f:
                log(f, "")
                log(f, "=" * 140)
                log(f, "BATCH_18A_SUCCESS = NO")
                log(f, "ERROR =", repr(exc))
                if DB.exists():
                    log(f, "DB_SHA_CURRENT =", sha256_file(DB))
                log(f, "DỪNG AN TOÀN.")
                log(f, "=" * 140)
        except Exception:
            print("ERROR =", repr(exc))
        rc = 1
    sys.exit(rc)
