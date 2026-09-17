from __future__ import annotations

from pathlib import Path
from datetime import datetime
import hashlib
import os
import py_compile
import shutil
import sqlite3

ROOT = Path(os.environ.get('PHOCAP_ROOT', r'C:\PhoCap'))
DB = ROOT / 'data' / 'phocap.db'
SERVICE = ROOT / 'app' / 'services' / 'finance_school_service.py'
TEMPLATE = ROOT / 'app' / 'templates' / 'report_inputs' / 'finance.html'
BASE = Path(__file__).resolve().parent
PAYLOAD_SERVICE = BASE / 'payload' / 'app' / 'services' / 'finance_school_service.py'
PAYLOAD_TEMPLATE = BASE / 'payload' / 'app' / 'templates' / 'report_inputs' / 'finance.html'

EXPECTED_BEFORE = {
    SERVICE: '2c44d47b326c7f9532311be4e71469ac7d950400a27886d1eaba604392b8547c',
    TEMPLATE: '92789c8b7f8f7b5060d9ced47c84e9ad7de72d7a7cc4b0d6f1f834a458e0ae8c',
}
EXPECTED_AFTER = {
    SERVICE: '6afe6a8aacb0da41f8d5e9d3c8f14f9db09d9a75ee63c81ec741d8d6bdd2c9a7',
    TEMPLATE: '397ebf6441ed8687d740e6ffe27f6faa7319b81116307f21ad9d9b85e2c98df1',
}
PAYLOADS = {
    SERVICE: PAYLOAD_SERVICE,
    TEMPLATE: PAYLOAD_TEMPLATE,
}


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def db_check() -> tuple[str, int, str]:
    if not DB.exists():
        return 'MISSING', -1, 'MISSING'
    before = sha(DB)
    uri = DB.resolve().as_uri() + '?mode=ro'
    con = sqlite3.connect(uri, uri=True)
    try:
        integrity = con.execute('PRAGMA integrity_check').fetchone()[0]
        fk = len(con.execute('PRAGMA foreign_key_check').fetchall())
    finally:
        con.close()
    return integrity, fk, before


def jinja_parse(path: Path) -> str:
    try:
        from jinja2 import Environment
        Environment().parse(path.read_text(encoding='utf-8'))
        return 'OK'
    except Exception as exc:
        return f'FAIL: {exc}'


print('=' * 118)
print('BÀI 33A.3 - ĐỊNH DẠNG SỐ TÀI CHÍNH KHÔNG LÀM TRÒN SAI')
print('CHỈ SỬA HIỂN THỊ WEB + EXCEL; KHÔNG ĐỔI GIÁ TRỊ DB, ROUTE, MENU HAY NGHIỆP VỤ KHÁC')
print('=' * 118)

for target, payload in PAYLOADS.items():
    if not target.exists():
        raise SystemExit(f'STOP_INSTALL: Không thấy {target}')
    if not payload.exists():
        raise SystemExit(f'STOP_INSTALL: Không thấy payload {payload}')

already = True
for target in EXPECTED_AFTER:
    if sha(target) != EXPECTED_AFTER[target]:
        already = False
        break
if already:
    print('ALREADY_INSTALLED = YES')
    print('INSTALL33A3_SUCCESS = YES')
    raise SystemExit(0)

for target, expected in EXPECTED_BEFORE.items():
    actual = sha(target)
    print(f'SHA_BEFORE {target.relative_to(ROOT)} =', actual)
    if actual != expected:
        print('EXPECTED_SHA_BEFORE =', expected)
        raise SystemExit(f'STOP_INSTALL: SHA {target.name} không đúng nền 33A/33A.1/33A.2 đã khóa. KHÔNG thay file.')

for target, payload in PAYLOADS.items():
    actual = sha(payload)
    print(f'PAYLOAD_SHA {payload.name} =', actual)
    if actual != EXPECTED_AFTER[target]:
        raise SystemExit(f'STOP_INSTALL: Payload {payload.name} không hợp lệ.')

integrity_before, fk_before, db_sha_before = db_check()
print('INTEGRITY_BEFORE =', integrity_before)
print('FK_COUNT_BEFORE =', fk_before)
if integrity_before != 'ok' or fk_before != 0:
    raise SystemExit('STOP_INSTALL: Database chưa đạt kiểm tra an toàn.')

stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
backup_dir = ROOT / 'backups' / f'source_33a_3_{stamp}'
for target in PAYLOADS:
    dst = backup_dir / target.relative_to(ROOT)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(target, dst)
print('BACKUP_DIR =', backup_dir)

try:
    for target, payload in PAYLOADS.items():
        shutil.copy2(payload, target)
        after = sha(target)
        print(f'SHA_AFTER {target.relative_to(ROOT)} =', after)
        if after != EXPECTED_AFTER[target]:
            raise RuntimeError(f'SHA sau cài đặt không đúng: {target}')

    py_compile.compile(str(SERVICE), doraise=True)
    print('PY_COMPILE = OK')

    parse = jinja_parse(TEMPLATE)
    print('JINJA_PARSE =', parse)
    if parse != 'OK':
        raise RuntimeError(parse)

    service_text = SERVICE.read_text(encoding='utf-8')
    template_text = TEMPLATE.read_text(encoding='utf-8')
    if 'BAI_33A_3_FINANCE_NUMBER_FORMAT_START' not in service_text:
        raise RuntimeError('Thiếu marker định dạng Excel 33A.3.')
    if 'finance_number_format = "#,##0.##"' not in service_text:
        raise RuntimeError('Thiếu định dạng #,##0.##.')
    if 'BAI_33A_3_FINANCE_INPUT_DISPLAY' not in template_text:
        raise RuntimeError('Thiếu marker hiển thị web 33A.3.')
    if ".rstrip('0').rstrip('.')" not in template_text:
        raise RuntimeError('Thiếu logic bỏ số 0 dư trên web.')

    integrity_after, fk_after, db_sha_after = db_check()
    print('INTEGRITY_AFTER =', integrity_after)
    print('FK_COUNT_AFTER =', fk_after)
    print('DB_SHA_UNCHANGED =', 'YES' if db_sha_after == db_sha_before else 'NO')
    if integrity_after != 'ok' or fk_after != 0 or db_sha_after != db_sha_before:
        raise RuntimeError('Database thay đổi hoặc lỗi kiểm tra an toàn.')

except Exception as exc:
    for target in PAYLOADS:
        src = backup_dir / target.relative_to(ROOT)
        if src.exists():
            shutil.copy2(src, target)
    print('ROLLBACK_SOURCE = YES')
    raise SystemExit(f'STOP_INSTALL: {exc}')

print('SOURCE_FILES_REPLACED = 2')
print('DATABASE_WRITES_THIS_RUN = 0')
print('SCHEMA_CHANGE = 0')
print('ROUTE_CHANGE = 0')
print('MENU_CHANGE = 0')
print('BUSINESS_LOGIC_CHANGE = 0')
print('EXCEL_DISPLAY_FORMAT = #,##0.##')
print('WEB_TRAILING_ZERO_TRIM = YES')
print('INSTALL33A3_SUCCESS = YES')
print('=' * 118)
