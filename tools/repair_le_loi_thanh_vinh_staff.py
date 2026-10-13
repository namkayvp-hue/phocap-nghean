"""Repair only staff proven by the 2025–2026 source roster and merger 411.

Default is a read-only preview. --apply backs up SQLite and records an audit.
No names/identifiers are printed or embedded in this script.
"""
import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sqlite3
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'data/school_merger_source_rosters/TH_2025_2026.json'
DB = ROOT / 'data/phocap.db'


def norm(value):
    return ' '.join(''.join(c for c in unicodedata.normalize('NFD', str(value or '').lower().replace('đ','d'))
                           if unicodedata.category(c) != 'Mn').split())


def birthday(value):
    for fmt in ('%d/%m/%Y', '%Y-%m-%d'):
        try:
            return datetime.strptime(str(value)[:10], fmt).date().isoformat()
        except ValueError:
            pass
    raise ValueError('Ngày sinh nguồn không hợp lệ; dừng để kiểm tra.')


def preview(db, source):
    entries = [r for r in source['rows'] if norm(r['commune_name']) == 'phuong thanh vinh'
               and norm(r['school_name']) == 'truong tieu hoc le loi']
    if len(entries) != 89 or len({str(r['staff_code']) for r in entries}) != 89:
        raise ValueError('Danh sách nguồn không khớp 89 mã duy nhất.')
    schools = {r['code']: r for r in db.execute(
        'SELECT s.*,c.name commune FROM schools s JOIN communes c ON c.id=s.commune_id '
        'WHERE s.code IN (?,?,?)', ('40412406','40431406','40431414'))}
    target, old, merged = (schools[c] for c in ('40412406','40431406','40431414'))
    if norm(target['commune']) != 'phuong thanh vinh' or not target['is_active']:
        raise ValueError('Trường đích không khớp Thành Vinh hoặc đã ngừng hoạt động.')
    if any(norm(s['commune']) != 'xa lam thanh' for s in (old,merged)):
        raise ValueError('Địa bàn trường nguồn không khớp.')
    years = {r['code']: r['id'] for r in db.execute('SELECT id,code FROM school_years')}
    operation = db.execute('SELECT * FROM school_merger_operations WHERE id=411').fetchone()
    if not operation or operation['target_school_id'] != merged['id'] or old['id'] not in json.loads(operation['source_school_ids_json']):
        raise ValueError('Lịch sử sáp nhập không khớp.')
    if operation['school_year_id'] != years['2026-2027']:
        raise ValueError('Năm sáp nhập không khớp.')
    expected = {years['2025-2026']:old['id'], years['2026-2027']:merged['id']}
    changes=[]; verified=[]
    for entry in entries:
        members = db.execute('SELECT * FROM staff_members WHERE ministry_staff_code=?', (str(entry['staff_code']),)).fetchall()
        if len(members) != 1:
            raise ValueError('Không tìm thấy duy nhất một hồ sơ cho mã nguồn.')
        member=members[0]
        if norm(member['full_name']) != norm(entry['full_name']) or birthday(member['date_of_birth']) != birthday(entry['date_of_birth']):
            raise ValueError('Tên/ngày sinh không khớp mã nguồn; dừng, không sửa.')
        rows=db.execute('SELECT * FROM staff_year_records WHERE staff_member_id=? AND school_year_id IN (?,?)',
                        (member['id'], *expected)).fetchall()
        if len(rows)!=2:
            raise ValueError('Thiếu hoặc trùng hồ sơ năm học.')
        for row in rows:
            if row['school_id'] not in (expected[row['school_year_id']], target['id']):
                raise ValueError('Hồ sơ đã chuyển sang trường khác; cần đối chiếu riêng.')
            verified.append(dict(row))
            if row['school_id'] != target['id']:
                changes.append(dict(row))
    return target['id'], old['id'], years, verified, changes


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    source=json.loads(SOURCE.read_text(encoding='utf-8'))
    db=sqlite3.connect(DB); db.row_factory=sqlite3.Row
    try:
        target,old,years,verified,changes=preview(db,source)
        print('Verified staff: 89; year records:',len(verified),'to repair:',len(changes))
        print('Position totals by year:',dict(Counter((r['school_year_id'],r['position_group']) for r in verified)))
        if not args.apply or not changes:
            return
        folder=ROOT/'backups'/('le_loi_thanh_vinh_'+datetime.now().strftime('%Y%m%d_%H%M%S'))
        folder.mkdir(parents=True,exist_ok=False)
        with sqlite3.connect(folder/'phocap_before.db') as backup:
            db.backup(backup)
        details={'source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
                 'reason':'Khôi phục đúng xã/trường từ danh sách nguồn; sửa gán nhầm trường trùng tên và hồ sơ kế thừa sáp nhập 411.',
                 'target_school_id':target,'before':changes}
        (folder/'audit_before.json').write_text(json.dumps(details,ensure_ascii=False,indent=2),encoding='utf-8')
        db.execute('BEGIN IMMEDIATE')
        _,_,_,_,fresh=preview(db,source)
        if fresh != changes:
            raise ValueError('Dữ liệu đã thay đổi trong khi sao lưu; dừng.')
        for row in changes:
            cursor=db.execute('UPDATE staff_year_records SET school_id=?,updated_at=? WHERE id=? AND school_id=?',
                              (target,datetime.now().isoformat(' '),row['id'],row['school_id']))
            if cursor.rowcount!=1:
                raise ValueError('Cập nhật không khớp số dòng.')
        _,_,_,after,pending=preview(db,source)
        if pending or len(after)!=178:
            raise ValueError('Kiểm tra sau cập nhật không đạt.')
        audit={'record_ids':[r['id'] for r in changes], 'source_sha256':details['source_sha256'],
               'reason':details['reason'], 'audit_before':str(folder/'audit_before.json')}
        db.execute('INSERT INTO school_merger_staff_repair_logs '
                   '(version,source_school_id,target_school_id,school_year_id,history_rows_repaired,current_rows_repaired,teacher_accounts_repaired,backup_name,details_json,created_at) '
                   'VALUES (?,?,?,?,?,?,?,?,?,?)',
                   ('LE_LOI_THANH_VINH_V1',old,target,years['2026-2027'],
                    sum(r['school_year_id']==years['2025-2026'] for r in changes),
                    sum(r['school_year_id']==years['2026-2027'] for r in changes),0,str(folder),
                    json.dumps(audit,ensure_ascii=False),datetime.now().isoformat(' ')))
        db.commit()
        print('Repaired',len(changes),'year records. Backup:',folder)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__=='__main__':
    main()
