# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

ROOT = Path(r'C:\PhoCap')
APP = ROOT / 'app'
DB = ROOT / 'data' / 'phocap.db'
EXPORTS = ROOT / 'exports'
ROUTER = APP / 'routers' / 'school_rename.py'
TEMPLATE = APP / 'templates' / 'data_tools' / 'school_rename.html'
MENU = APP / 'templates' / 'partials' / 'dropdown_menu_v1.html'
MAIN = APP / 'main.py'
OUT = EXPORTS / 'KHAO_SAT_NGHIEP_VU_DOI_TEN_TRUONG_32A.txt'

TRI_LE_CODE = '40415412'
TRI_LE_OLD = 'Trường PTDTBT TH Tri Lễ 2'
TRI_LE_NEW = 'Tiểu học Tri Lễ'


def sha256_file(path: Path) -> str | None:
    if not path.exists():
        return None
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def read_text(path: Path) -> str:
    return path.read_text(encoding='utf-8-sig', errors='ignore')


def log(f, *parts):
    line = ' '.join(str(x) for x in parts)
    print(line)
    f.write(line + '\n')
    f.flush()


def inspect_db():
    con = sqlite3.connect(f'file:{DB.as_posix()}?mode=ro', uri=True, timeout=30)
    con.row_factory = sqlite3.Row
    try:
        integrity = con.execute('PRAGMA integrity_check').fetchone()[0]
        fk = con.execute('PRAGMA foreign_key_check').fetchall()
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        years = [dict(r) for r in con.execute('SELECT * FROM school_years ORDER BY id').fetchall()] if 'school_years' in tables else []
        schema = [dict(r) for r in con.execute('PRAGMA table_info(school_name_histories)').fetchall()] if 'school_name_histories' in tables else []
        history = []
        if 'school_name_histories' in tables:
            history = [dict(r) for r in con.execute('''
                SELECT h.id,h.school_id,h.effective_school_year_id,h.old_name,h.new_name,
                       h.changed_at,h.changed_by_user_id,s.code AS school_code,
                       s.name AS current_name,y.code AS effective_year_code
                FROM school_name_histories h
                JOIN schools s ON s.id=h.school_id
                JOIN school_years y ON y.id=h.effective_school_year_id
                ORDER BY h.id DESC LIMIT 100
            ''').fetchall()]
        tri_le = [dict(r) for r in con.execute('''
            SELECT id,code,name,commune_id,is_active FROM schools
            WHERE code=? OR name IN (?,?) ORDER BY id
        ''', (TRI_LE_CODE, TRI_LE_OLD, TRI_LE_NEW)).fetchall()] if 'schools' in tables else []
        tri_hist = []
        if 'school_name_histories' in tables and tri_le:
            ids = [int(x['id']) for x in tri_le]
            marks = ','.join('?' for _ in ids)
            tri_hist = [dict(r) for r in con.execute(f'''
                SELECT h.*,y.code AS effective_year_code
                FROM school_name_histories h
                JOIN school_years y ON y.id=h.effective_school_year_id
                WHERE h.school_id IN ({marks}) ORDER BY h.id
            ''', ids).fetchall()]
    finally:
        con.close()
    return {
        'integrity': integrity,
        'fk_count': len(fk),
        'history_table_exists': 'school_name_histories' in tables,
        'history_schema': schema,
        'history_rows': history,
        'school_years': years,
        'tri_le_school': tri_le,
        'tri_le_history': tri_hist,
    }


def scan_history_usage():
    out = []
    for p in APP.rglob('*.py'):
        if '__pycache__' in p.parts:
            continue
        try:
            text = read_text(p)
        except Exception:
            continue
        if 'school_name_histories' in text:
            out.append({
                'file': str(p.relative_to(ROOT)),
                'lines': [i for i, line in enumerate(text.splitlines(), 1) if 'school_name_histories' in line],
            })
    return out


def main():
    EXPORTS.mkdir(parents=True, exist_ok=True)
    with OUT.open('w', encoding='utf-8-sig', newline='\n') as f:
        log(f, '=' * 180)
        log(f, 'BÀI 32A - KHẢO SÁT NGHIỆP VỤ ĐỔI TÊN TRƯỜNG')
        log(f, 'CHỈ ĐỌC SOURCE + DATABASE - KHÔNG SỬA SOURCE - KHÔNG GHI DATABASE')
        log(f, '=' * 180)
        if not DB.exists():
            raise RuntimeError(f'Không tìm thấy DB: {DB}')

        db_sha_before = sha256_file(DB)
        db = inspect_db()
        log(f, 'DB_SHA_BEFORE =', db_sha_before)
        log(f, 'INTEGRITY =', db['integrity'])
        log(f, 'FK_COUNT =', db['fk_count'])

        files = {'ROUTER': ROUTER, 'TEMPLATE': TEMPLATE, 'MENU': MENU, 'MAIN': MAIN}
        log(f, '')
        log(f, 'I. SOURCE HIỆN TẠI')
        for name, path in files.items():
            log(f, name, 'EXISTS =', path.exists(), 'SHA =', sha256_file(path))

        router_text = read_text(ROUTER) if ROUTER.exists() else ''
        template_text = read_text(TEMPLATE) if TEMPLATE.exists() else ''
        menu_text = read_text(MENU) if MENU.exists() else ''
        main_text = read_text(MAIN) if MAIN.exists() else ''

        checks = {
            'ROUTER_PREFIX': 'prefix="/cong-cu-du-lieu/doi-ten-truong"' in router_text,
            'ADMIN_ONLY': 'is_admin_role' in router_text,
            'HISTORY_TABLE_CODE': 'school_name_histories' in router_text,
            'EFFECTIVE_YEAR': 'effective_school_year_id' in router_text,
            'BACKUP_DATABASE': '_backup_database' in router_text,
            'BEGIN_IMMEDIATE': 'BEGIN IMMEDIATE' in router_text,
            'INTEGRITY_CHECK': 'PRAGMA integrity_check' in router_text,
            'FK_CHECK': 'PRAGMA foreign_key_check' in router_text,
            'UPDATE_NAME_ONLY': 'UPDATE schools SET name=' in router_text,
            'DOES_NOT_UPDATE_CODE': 'UPDATE schools SET code=' not in router_text,
            'DOES_NOT_UPDATE_COMMUNE': 'UPDATE schools SET commune_id=' not in router_text,
            'DOES_NOT_UPDATE_ACTIVE': 'UPDATE schools SET is_active=' not in router_text,
            'OLD_NAME_UI': 'Tên cũ' in template_text,
            'NEW_NAME_UI': 'Tên mới' in template_text,
            'NO_DOCUMENT_NUMBER_UI': 'Số/Ký hiệu văn bản' not in template_text,
            'NO_DOCUMENT_DATE_UI': 'Ngày văn bản' not in template_text,
            'NO_REASON_UI': 'Lý do' not in template_text,
            'NO_NOTE_UI': 'Ghi chú' not in template_text,
            'HISTORY_UI': 'Lịch sử đổi tên trường' in template_text,
            'AUTOCOMPLETE_COMMUNE': 'Gõ từ đầu tên xã/phường' in template_text,
            'AUTOCOMPLETE_SCHOOL': 'Gõ từ đầu tên trường' in template_text,
            'MENU_LINK': '/cong-cu-du-lieu/doi-ten-truong' in menu_text,
            'MAIN_ROUTER': 'school_rename_router' in main_text,
        }
        for k, v in checks.items():
            log(f, k, '=', 'YES' if v else 'NO')

        log(f, '')
        log(f, 'II. DATABASE / LỊCH SỬ')
        log(f, 'HISTORY_TABLE_EXISTS =', db['history_table_exists'])
        log(f, 'HISTORY_SCHEMA =', json.dumps(db['history_schema'], ensure_ascii=False, indent=2, default=str))
        log(f, 'HISTORY_ROWS =', json.dumps(db['history_rows'], ensure_ascii=False, indent=2, default=str))
        log(f, 'SCHOOL_YEARS =', json.dumps(db['school_years'], ensure_ascii=False, indent=2, default=str))

        log(f, '')
        log(f, 'III. CA ĐỔI TÊN RIÊNG QĐ3805 - TRI LỄ')
        log(f, 'TRI_LE_SCHOOL =', json.dumps(db['tri_le_school'], ensure_ascii=False, indent=2, default=str))
        log(f, 'TRI_LE_HISTORY =', json.dumps(db['tri_le_history'], ensure_ascii=False, indent=2, default=str))

        usage = scan_history_usage()
        log(f, '')
        log(f, 'IV. NƠI ĐANG DÙNG school_name_histories')
        log(f, json.dumps(usage, ensure_ascii=False, indent=2, default=str))

        basic_ready = all(checks.values()) and db['history_table_exists'] and db['integrity'] == 'ok' and db['fk_count'] == 0
        history_used_outside_rename = any(x['file'].replace('\\','/') != 'app/routers/school_rename.py' for x in usage)

        log(f, '')
        log(f, 'V. KẾT LUẬN 32A')
        log(f, 'BASIC_RENAME_FEATURE_READY =', 'YES' if basic_ready else 'NO')
        log(f, 'HISTORY_USED_OUTSIDE_RENAME =', 'YES' if history_used_outside_rename else 'NO')
        log(f, 'HISTORICAL_NAME_RESOLUTION_GAP_POSSIBLE =', 'NO' if history_used_outside_rename else 'YES')
        log(f, 'NEEDS_32B_COMPLETION_PATCH =', 'NO' if basic_ready and history_used_outside_rename else 'YES')
        log(f, '')
        log(f, 'NGUYÊN TẮC KHÓA:')
        log(f, '- Chỉ Tên cũ -> Tên mới.')
        log(f, '- Giữ nguyên school_id, mã trường, xã/phường, cấp học, trạng thái và dữ liệu liên kết.')
        log(f, '- Năm hiệu lực lấy từ năm học đang chọn.')
        log(f, '- Có xem trước, backup, transaction, integrity/FK, lịch sử.')
        log(f, '- Không chạy qua engine sáp nhập.')
        log(f, '- Tên lịch sử theo năm phải tra được từ school_name_histories trước khi xử lý nguồn học sinh.')
        log(f, '')
        log(f, 'DATABASE_WRITES_THIS_RUN = 0')
        log(f, 'SOURCE_WRITES_THIS_RUN = 0')
        log(f, 'DB_SHA_AFTER =', sha256_file(DB))
        log(f, 'AUDIT32A_SUCCESS = YES')
        log(f, '=' * 180)

if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        try:
            EXPORTS.mkdir(parents=True, exist_ok=True)
            with OUT.open('a', encoding='utf-8-sig', newline='\n') as f:
                log(f, '')
                log(f, '=' * 180)
                log(f, 'AUDIT32A_SUCCESS = NO')
                log(f, 'ERROR =', repr(exc))
                if DB.exists():
                    log(f, 'DB_SHA_CURRENT =', sha256_file(DB))
                log(f, 'DỪNG AN TOÀN.')
                log(f, '=' * 180)
        except Exception:
            print('ERROR =', repr(exc))
        raise
