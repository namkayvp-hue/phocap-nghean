from pathlib import Path
import hashlib
import os
import py_compile
import sqlite3

ROOT = Path(os.environ.get('PHOCAP_ROOT', r'C:\PhoCap'))
DB = ROOT / 'data' / 'phocap.db'
SERVICE = ROOT / 'app' / 'services' / 'finance_school_service.py'
TEMPLATE = ROOT / 'app' / 'templates' / 'report_inputs' / 'finance.html'
EXPECTED_SERVICE = '6afe6a8aacb0da41f8d5e9d3c8f14f9db09d9a75ee63c81ec741d8d6bdd2c9a7'
EXPECTED_TEMPLATE = '397ebf6441ed8687d740e6ffe27f6faa7319b81116307f21ad9d9b85e2c98df1'


def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()

print('=' * 118)
print('AUDIT BÀI 33A.3 - CHỈ ĐỌC')
print('=' * 118)

service_sha = sha(SERVICE)
template_sha = sha(TEMPLATE)
service_text = SERVICE.read_text(encoding='utf-8')
template_text = TEMPLATE.read_text(encoding='utf-8')
print('SERVICE_SHA =', service_sha)
print('TEMPLATE_SHA =', template_sha)
print('SOURCE_SHA_OK =', 'YES' if service_sha == EXPECTED_SERVICE and template_sha == EXPECTED_TEMPLATE else 'NO')
print('EXCEL_NUMBER_FORMAT =', 'YES' if 'finance_number_format = "#,##0.##"' in service_text else 'NO')
print('WEB_TRIM_TRAILING_ZERO =', 'YES' if ".rstrip('0').rstrip('.')" in template_text else 'NO')
print('MARKERS_OK =', 'YES' if 'BAI_33A_3_FINANCE_NUMBER_FORMAT_START' in service_text and 'BAI_33A_3_FINANCE_INPUT_DISPLAY' in template_text else 'NO')

try:
    py_compile.compile(str(SERVICE), doraise=True)
    print('PY_COMPILE = OK')
    py_ok = True
except Exception as exc:
    print('PY_COMPILE = FAIL:', exc)
    py_ok = False

try:
    from jinja2 import Environment
    Environment().parse(template_text)
    print('JINJA_PARSE = OK')
    jinja_ok = True
except Exception as exc:
    print('JINJA_PARSE = FAIL:', exc)
    jinja_ok = False

db_before = sha(DB)
uri = DB.resolve().as_uri() + '?mode=ro'
con = sqlite3.connect(uri, uri=True)
try:
    integrity = con.execute('PRAGMA integrity_check').fetchone()[0]
    fk = len(con.execute('PRAGMA foreign_key_check').fetchall())
finally:
    con.close()
db_after = sha(DB)
print('INTEGRITY =', integrity)
print('FK_COUNT =', fk)
print('DATABASE_WRITES_THIS_RUN = 0')
print('DB_SHA_UNCHANGED =', 'YES' if db_before == db_after else 'NO')

ok = all([
    service_sha == EXPECTED_SERVICE,
    template_sha == EXPECTED_TEMPLATE,
    'finance_number_format = "#,##0.##"' in service_text,
    ".rstrip('0').rstrip('.')" in template_text,
    'BAI_33A_3_FINANCE_NUMBER_FORMAT_START' in service_text,
    'BAI_33A_3_FINANCE_INPUT_DISPLAY' in template_text,
    py_ok,
    jinja_ok,
    integrity == 'ok',
    fk == 0,
    db_before == db_after,
])
print('AUDIT33A3_SUCCESS =', 'YES' if ok else 'NO')
print('=' * 118)
