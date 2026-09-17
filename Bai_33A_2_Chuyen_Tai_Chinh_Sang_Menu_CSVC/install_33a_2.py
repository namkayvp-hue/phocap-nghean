from __future__ import annotations

from pathlib import Path
from datetime import datetime
import hashlib
import shutil
import sqlite3
import sys

ROOT = Path(r"C:\PhoCap")
TARGET = ROOT / "app" / "templates" / "partials" / "dropdown_menu_v1.html"
DB = ROOT / "data" / "phocap.db"
PAYLOAD = Path(__file__).resolve().parent / "payload" / "app" / "templates" / "partials" / "dropdown_menu_v1.html"
EXPECTED_BEFORE = "7386a35193f88230078438aaef3ba8da83c71394a3f784704dd8e003b205111f"
EXPECTED_AFTER = "6b9a40df39a6b260ebf69aef5de547f49c0a668b6044ce670e2c2777874a2693"


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def db_check() -> tuple[str, int, str]:
    if not DB.exists():
        return "MISSING", -1, "MISSING"
    before = sha(DB)
    uri = DB.resolve().as_uri() + "?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    try:
        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
        fk = len(con.execute("PRAGMA foreign_key_check").fetchall())
    finally:
        con.close()
    return integrity, fk, before


def jinja_parse(path: Path) -> str:
    try:
        from jinja2 import Environment
        Environment().parse(path.read_text(encoding="utf-8"))
        return "OK"
    except Exception as exc:
        return f"FAIL: {exc}"


print("=" * 118)
print("BÀI 33A.2 - CHUYỂN NHẬP DỮ LIỆU BC-TÀI CHÍNH SANG CUỐI MENU CSVC")
print("CHỈ ĐỔI VỊ TRÍ MENU - KHÔNG ĐỔI ROUTE - KHÔNG GHI DỮ LIỆU NGHIỆP VỤ")
print("=" * 118)

if not TARGET.exists():
    raise SystemExit(f"STOP_INSTALL: Không thấy {TARGET}")
if not PAYLOAD.exists():
    raise SystemExit(f"STOP_INSTALL: Không thấy payload {PAYLOAD}")

before_sha = sha(TARGET)
payload_sha = sha(PAYLOAD)
print("MENU_SHA_BEFORE =", before_sha)
print("PAYLOAD_SHA =", payload_sha)

if before_sha == EXPECTED_AFTER:
    print("ALREADY_INSTALLED = YES")
    print("INSTALL33A2_SUCCESS = YES")
    raise SystemExit(0)

if before_sha != EXPECTED_BEFORE:
    print("EXPECTED_SHA_BEFORE =", EXPECTED_BEFORE)
    raise SystemExit("STOP_INSTALL: SHA menu hiện tại không đúng nền Bài 33A đã khóa. KHÔNG thay file.")
if payload_sha != EXPECTED_AFTER:
    raise SystemExit("STOP_INSTALL: SHA payload không hợp lệ.")

integrity_before, fk_before, db_sha_before = db_check()
print("INTEGRITY_BEFORE =", integrity_before)
print("FK_COUNT_BEFORE =", fk_before)
if integrity_before != "ok" or fk_before != 0:
    raise SystemExit("STOP_INSTALL: Database chưa đạt kiểm tra an toàn.")

stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
backup_dir = ROOT / "backups" / f"source_33a_2_{stamp}"
backup_file = backup_dir / "app" / "templates" / "partials" / "dropdown_menu_v1.html"
backup_file.parent.mkdir(parents=True, exist_ok=True)
shutil.copy2(TARGET, backup_file)
print("BACKUP =", backup_file)

try:
    shutil.copy2(PAYLOAD, TARGET)
    after_sha = sha(TARGET)
    print("MENU_SHA_AFTER =", after_sha)
    if after_sha != EXPECTED_AFTER:
        raise RuntimeError("SHA sau cài đặt không đúng.")

    parse = jinja_parse(TARGET)
    print("JINJA_PARSE =", parse)
    if parse != "OK":
        raise RuntimeError(parse)

    text = TARGET.read_text(encoding="utf-8")
    required = [
        "BAI_33A_2_FINANCE_IN_CSVC_ADMIN_START",
        "BAI_33A_2_FINANCE_IN_CSVC_SCHOOL_START",
        "CSVC.4. Nhập dữ liệu BC-Tài chính",
        "CSVC.6. Nhập dữ liệu BC-Tài chính",
        "href=\"/bao-cao/tai-chinh/nhap\"",
    ]
    if not all(x in text for x in required):
        raise RuntimeError("Thiếu marker/menu Bài 33A.2.")
    if "5.2.8. Nhập dữ liệu BC-Tài chính" in text:
        raise RuntimeError("Mục 5.2.8 cũ vẫn còn trong menu Báo cáo.")

    integrity_after, fk_after, db_sha_after = db_check()
    print("INTEGRITY_AFTER =", integrity_after)
    print("FK_COUNT_AFTER =", fk_after)
    print("DB_SHA_UNCHANGED =", "YES" if db_sha_after == db_sha_before else "NO")
    if integrity_after != "ok" or fk_after != 0 or db_sha_after != db_sha_before:
        raise RuntimeError("Database thay đổi hoặc lỗi kiểm tra an toàn.")

except Exception as exc:
    shutil.copy2(backup_file, TARGET)
    print("ROLLBACK_SOURCE = YES")
    raise SystemExit(f"STOP_INSTALL: {exc}")

print("SOURCE_FILES_REPLACED = 1")
print("DATABASE_WRITES_THIS_RUN = 0")
print("ROUTE_CHANGE = 0")
print("BUSINESS_LOGIC_CHANGE = 0")
print("INSTALL33A2_SUCCESS = YES")
print("=" * 118)
