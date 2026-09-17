from __future__ import annotations

from pathlib import Path
from datetime import datetime
import hashlib
import py_compile
import shutil
import sqlite3
import sys

PROJECT = Path(r"C:\PhoCap")
TARGET = PROJECT / "app" / "access_control.py"
REPORT_INPUTS = PROJECT / "app" / "routers" / "report_inputs.py"
DB = PROJECT / "data" / "phocap.db"
PAYLOAD = Path(__file__).resolve().parent / "payload" / "app" / "access_control.py"

ACCESS_BEFORE = "a7cee182df3b80e77729d1f98232e97c7bee0a1bae2b70ff701afaa517737e2c"
ACCESS_AFTER = "02e6c30089e7243c7a3fe6c7d16a0bf1a27868ee7037cbe4c1157c157a12d22d"
REPORT_INPUTS_33A = "be29d7d788d75384731ed39964702d6b97a696128a66780d92b909f9c5d39e38"


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def db_checks() -> tuple[str, int]:
    if not DB.exists():
        return "MISSING", -1
    con = sqlite3.connect(DB.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
        fk_count = len(con.execute("PRAGMA foreign_key_check").fetchall())
        return str(integrity), fk_count
    finally:
        con.close()


def stop(msg: str) -> None:
    print("=" * 118)
    print("STOP_INSTALL_33A_1")
    print(msg)
    print("KHONG GHI DATABASE. KHONG THAY DOI SOURCE THEM.")
    print("=" * 118)
    raise SystemExit(2)


print("=" * 118)
print("BÀI 33A.1 - MỞ ĐÚNG QUYỀN POST NHẬP TÀI CHÍNH CHO TÀI KHOẢN TRƯỜNG")
print("Phạm vi: CHỈ app/access_control.py. KHÔNG sửa DB. KHÔNG đụng phân hệ khác.")
print("=" * 118)

for p, label in [(TARGET, "access_control.py"), (REPORT_INPUTS, "report_inputs.py"), (PAYLOAD, "payload")]:
    if not p.exists():
        stop(f"Thiếu {label}: {p}")

access_before = sha(TARGET)
report_sha = sha(REPORT_INPUTS)
db_sha_before = sha(DB) if DB.exists() else "MISSING"
print("ACCESS_SHA_BEFORE =", access_before)
print("REPORT_INPUTS_SHA =", report_sha)
print("DB_SHA_BEFORE =", db_sha_before)

if report_sha != REPORT_INPUTS_33A:
    stop("report_inputs.py không đúng nền Bài 33A đã audit. Dừng để bảo vệ source hiện tại.")

if access_before == ACCESS_AFTER:
    print("ALREADY_INSTALLED = YES")
    py_compile.compile(str(TARGET), doraise=True)
    integrity, fk_count = db_checks()
    db_sha_after = sha(DB) if DB.exists() else "MISSING"
    print("PY_COMPILE = OK")
    print("INTEGRITY =", integrity)
    print("FK_COUNT =", fk_count)
    print("DB_SHA_UNCHANGED =", "YES" if db_sha_before == db_sha_after else "NO")
    print("DATABASE_WRITES_THIS_RUN = 0")
    print("INSTALL33A1_SUCCESS = YES")
    raise SystemExit(0)

if access_before != ACCESS_BEFORE:
    stop("SHA access_control.py khác nền đã khóa. Không tự ghi đè file đang có thay đổi khác.")

if sha(PAYLOAD) != ACCESS_AFTER:
    stop("Payload access_control.py sai SHA.")

backup_dir = PROJECT / "backups" / ("source_33a_1_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
backup_dir.mkdir(parents=True, exist_ok=False)
backup_file = backup_dir / "access_control.py"
shutil.copy2(TARGET, backup_file)
print("BACKUP =", backup_file)

try:
    shutil.copy2(PAYLOAD, TARGET)
    py_compile.compile(str(TARGET), doraise=True)
    if sha(TARGET) != ACCESS_AFTER:
        raise RuntimeError("SHA sau cài không đúng payload")
except Exception as exc:
    shutil.copy2(backup_file, TARGET)
    print("ROLLBACK = YES")
    stop(f"Cài đặt lỗi, đã khôi phục source cũ: {exc}")

integrity, fk_count = db_checks()
db_sha_after = sha(DB) if DB.exists() else "MISSING"
print("ACCESS_SHA_AFTER =", sha(TARGET))
print("PY_COMPILE = OK")
print("INTEGRITY_AFTER =", integrity)
print("FK_COUNT_AFTER =", fk_count)
print("DB_SHA_AFTER =", db_sha_after)
print("DB_SHA_UNCHANGED =", "YES" if db_sha_before == db_sha_after else "NO")
print("SOURCE_FILES_REPLACED = 1")
print("SCHEMA_CHANGE = 0")
print("BUSINESS_DATA_WRITE = 0")
print("DATABASE_WRITES_THIS_RUN = 0")

ok = (
    sha(TARGET) == ACCESS_AFTER
    and integrity == "ok"
    and fk_count == 0
    and db_sha_before == db_sha_after
)
print("INSTALL33A1_SUCCESS =", "YES" if ok else "NO")
print("=" * 118)
if not ok:
    raise SystemExit(3)
