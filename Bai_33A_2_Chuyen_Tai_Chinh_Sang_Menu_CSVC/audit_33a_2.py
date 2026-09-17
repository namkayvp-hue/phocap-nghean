from pathlib import Path
import hashlib
import sqlite3

ROOT = Path(r"C:\PhoCap")
TARGET = ROOT / "app" / "templates" / "partials" / "dropdown_menu_v1.html"
DB = ROOT / "data" / "phocap.db"
EXPECTED = "6b9a40df39a6b260ebf69aef5de547f49c0a668b6044ce670e2c2777874a2693"

def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024*1024), b""):
            h.update(chunk)
    return h.hexdigest()

print("=" * 118)
print("AUDIT BÀI 33A.2 - CHỈ ĐỌC")
print("=" * 118)
menu_sha = sha(TARGET)
text = TARGET.read_text(encoding="utf-8")
print("MENU_SHA =", menu_sha)
print("SOURCE_SHA_OK =", "YES" if menu_sha == EXPECTED else "NO")
print("OLD_5_2_8_REMOVED =", "YES" if "5.2.8. Nhập dữ liệu BC-Tài chính" not in text else "NO")
print("FINANCE_LINK_COUNT =", text.count('href="/bao-cao/tai-chinh/nhap"'))
print("CSVC_ADMIN_POSITION =", "YES" if "CSVC.4. Nhập dữ liệu BC-Tài chính" in text else "NO")
print("CSVC_SCHOOL_POSITION =", "YES" if "CSVC.6. Nhập dữ liệu BC-Tài chính" in text else "NO")
print("MN_SCHOOL_SCOPE =", "YES" if "menu_role == 'TRUONG' and (menu_school_mn or (not menu_school_th and not menu_school_thcs))" in text else "NO")
print("CSVC_ACTIVE_ON_FINANCE =", "YES" if "menu_path.startswith('/csvc') or menu_path == '/bao-cao/tai-chinh/nhap'" in text else "NO")
try:
    from jinja2 import Environment
    Environment().parse(text)
    print("JINJA_PARSE = OK")
    jinja_ok = True
except Exception as exc:
    print("JINJA_PARSE = FAIL:", exc)
    jinja_ok = False

db_before = sha(DB)
uri = DB.resolve().as_uri() + "?mode=ro"
con = sqlite3.connect(uri, uri=True)
try:
    integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
    fk = len(con.execute("PRAGMA foreign_key_check").fetchall())
finally:
    con.close()
db_after = sha(DB)
print("INTEGRITY =", integrity)
print("FK_COUNT =", fk)
print("DATABASE_WRITES_THIS_RUN = 0")
print("DB_SHA_UNCHANGED =", "YES" if db_before == db_after else "NO")

ok = all([
    menu_sha == EXPECTED,
    "5.2.8. Nhập dữ liệu BC-Tài chính" not in text,
    text.count('href="/bao-cao/tai-chinh/nhap"') == 2,
    "CSVC.4. Nhập dữ liệu BC-Tài chính" in text,
    "CSVC.6. Nhập dữ liệu BC-Tài chính" in text,
    "menu_role == 'TRUONG' and (menu_school_mn or (not menu_school_th and not menu_school_thcs))" in text,
    jinja_ok,
    integrity == "ok",
    fk == 0,
    db_before == db_after,
])
print("AUDIT33A2_SUCCESS =", "YES" if ok else "NO")
print("=" * 118)
