from __future__ import annotations

from pathlib import Path
import hashlib
import py_compile
import sqlite3

PROJECT = Path(r"C:\PhoCap")
ACCESS = PROJECT / "app" / "access_control.py"
REPORT_INPUTS = PROJECT / "app" / "routers" / "report_inputs.py"
DB = PROJECT / "data" / "phocap.db"
EXPECTED_ACCESS = "02e6c30089e7243c7a3fe6c7d16a0bf1a27868ee7037cbe4c1157c157a12d22d"
EXPECTED_REPORT = "be29d7d788d75384731ed39964702d6b97a696128a66780d92b909f9c5d39e38"
START = "# === BAI_33A_1_SCHOOL_FINANCE_POST_ACCESS_START ==="
END = "# === BAI_33A_1_SCHOOL_FINANCE_POST_ACCESS_END ==="


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

print("=" * 118)
print("AUDIT BÀI 33A.1 - CHỈ ĐỌC")
print("=" * 118)

access_text = ACCESS.read_text(encoding="utf-8")
report_text = REPORT_INPUTS.read_text(encoding="utf-8")
db_before = sha(DB) if DB.exists() else "MISSING"

py_compile.compile(str(ACCESS), doraise=True)

source_sha_ok = sha(ACCESS) == EXPECTED_ACCESS
report_sha_ok = sha(REPORT_INPUTS) == EXPECTED_REPORT
markers_ok = access_text.count(START) == 1 and access_text.count(END) == 1
special = 'if normalized_path == "/bao-cao/tai-chinh/nhap":' in access_text
school_post = "return role_code == SCHOOL_ROLE_CODE" in access_text
route_post = '@router.post("/bao-cao/tai-chinh/nhap")' in report_text
own_scope = "if school_id != own_school_id:" in report_text

con = sqlite3.connect(DB.resolve().as_uri() + "?mode=ro", uri=True)
try:
    integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
    fk_count = len(con.execute("PRAGMA foreign_key_check").fetchall())
finally:
    con.close()

db_after = sha(DB) if DB.exists() else "MISSING"

print("ACCESS_SHA =", sha(ACCESS))
print("REPORT_INPUTS_SHA_OK =", "YES" if report_sha_ok else "NO")
print("SOURCE_SHA_OK =", "YES" if source_sha_ok else "NO")
print("MARKERS_OK =", "YES" if markers_ok else "NO")
print("FINANCE_POST_MIDDLEWARE_RULE =", "YES" if special else "NO")
print("SCHOOL_POST_ALLOWED =", "YES" if school_post else "NO")
print("ROUTER_POST_EXISTS =", "YES" if route_post else "NO")
print("SCHOOL_OWN_SCOPE_LOCK =", "YES" if own_scope else "NO")
print("PY_COMPILE = OK")
print("INTEGRITY =", integrity)
print("FK_COUNT =", fk_count)
print("DATABASE_WRITES_THIS_RUN = 0")
print("DB_SHA_UNCHANGED =", "YES" if db_before == db_after else "NO")

ok = all([
    source_sha_ok, report_sha_ok, markers_ok, special, school_post,
    route_post, own_scope, integrity == "ok", fk_count == 0,
    db_before == db_after,
])
print("AUDIT33A1_SUCCESS =", "YES" if ok else "NO")
print("=" * 118)
if not ok:
    raise SystemExit(2)
