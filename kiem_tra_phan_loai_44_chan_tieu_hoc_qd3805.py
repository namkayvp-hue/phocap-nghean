from __future__ import annotations

import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

PROJECT_DIR = Path(__file__).resolve().parent
if not (PROJECT_DIR / 'app').exists():
    PROJECT_DIR = Path.cwd()
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from app.database import DATABASE_PATH  # noqa: E402
from app.services import school_merger_service as engine  # noqa: E402
from app.services import school_merger_level_batch_service as batch  # noqa: E402

TARGET_YEAR = '2026-2027'
TARGET_LEVEL = 'TH'
OUT_DIR = PROJECT_DIR / 'exports' / 'Kiem_Tra_44_Chan_Tieu_Hoc_QD3805'


def norm(value: Any) -> str:
    text = str(value or '').strip().lower().replace('đ', 'd')
    text = ''.join(ch for ch in unicodedata.normalize('NFD', text) if unicodedata.category(ch) != 'Mn')
    text = text.replace('&', ' va ')
    text = re.sub(r'[^a-z0-9]+', ' ', text)
    text = re.sub(r'\btruong\b', ' ', text)
    return ' '.join(text.split())


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def year_id() -> int:
    for y in engine.list_school_years():
        code = str(y.get('code') or y.get('name') or '').replace('–', '-').replace('—', '-')
        if code == TARGET_YEAR:
            return int(y['id'])
    raise RuntimeError(f'Không tìm thấy năm học {TARGET_YEAR}.')


def categorize(reasons: list[str]) -> list[str]:
    cats = set()
    joined = ' | '.join(reasons).lower()
    if 'chưa khớp tên trường db' in joined or 'khớp ' in joined and 'trường' in joined:
        cats.add('KHOP_TEN_TRUONG_DB')
    if 'không xác định được trường nguồn/đích' in joined or 'xác định rõ trường nguồn' in joined:
        cats.add('CHUA_XAC_DINH_NGUON_DICH')
    if 'không đạt kiểm tra dữ liệu nguồn' in joined:
        cats.add('KIEM_TRA_NGUON')
    if 'trùng' in joined or 'duplicate' in joined:
        cats.add('TRUNG_GHEP_HOAC_DU_LIEU')
    if 'không lập được bản xem trước' in joined or 'mô phỏng' in joined or 'bản xem trước' in joined:
        cats.add('XEM_TRUOC_MO_PHONG')
    if not cats:
        cats.add('KHAC')
    return sorted(cats)


def member_names(plan: dict[str, Any]) -> list[str]:
    out = []
    for x in plan.get('member_schools') or []:
        name = str((x or {}).get('excel_name') or (x or {}).get('name') or '').strip()
        if name and name not in out:
            out.append(name)
    return out


def candidate_suggestions(plan: dict[str, Any], schools: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    commune = norm(plan.get('commune_excel'))
    same = [s for s in schools if not commune or norm(s.get('commune_name')) == commune]
    pool = same or schools
    result: dict[str, list[dict[str, Any]]] = {}
    for name in member_names(plan):
        nn = norm(name)
        scored = []
        for s in pool:
            sn = norm(s.get('name'))
            if not nn or not sn:
                continue
            ratio = SequenceMatcher(None, nn, sn).ratio()
            # boost containment for common prefix variations such as "Trường Tiểu học ..."
            if nn in sn or sn in nn:
                ratio = max(ratio, 0.93)
            if ratio >= 0.62:
                scored.append((ratio, s))
        scored.sort(key=lambda z: (z[0], str(z[1].get('name') or '')), reverse=True)
        result[name] = [
            {
                'school_id': int(s.get('id')),
                'code': str(s.get('code') or ''),
                'name': str(s.get('name') or ''),
                'commune': str(s.get('commune_name') or ''),
                'is_active': bool(s.get('is_active')),
                'score': round(float(score), 4),
            }
            for score, s in scored[:3]
        ]
    return result


def main() -> None:
    print('=' * 108)
    print('KIỂM TRA / PHÂN LOẠI 44 NỘI DUNG CHẶN - TIỂU HỌC - QĐ3805')
    print(f'Dự án: {PROJECT_DIR}')
    print(f'Database: {DATABASE_PATH}')
    print('Chế độ: CHỈ ĐỌC / KHÔNG SỬA MÃ NGUỒN / KHÔNG GHI DATABASE')
    print('=' * 108)

    yid = year_id()
    preview = batch.build_level_batch_preview(school_year_id=yid, level_code=TARGET_LEVEL)
    counts = dict(preview.get('counts') or {})
    registry = dict(preview.get('registry') or {})

    all_schools = engine.list_schools(year_id=yid, commune_id=None, level_code=None, include_inactive=True)

    mapped_block_rows = []
    seen_ops = set()
    for p in preview.get('rows') or []:
        if str(p.get('batch_state') or '').upper() != 'BLOCK':
            continue
        op_id = str(p.get('qd3805_operation_id') or '')
        # report every internal row, but mark whether this is the first occurrence of the QĐ3805 operation
        reasons = [str(x) for x in (p.get('batch_blockers') or []) if str(x).strip()]
        item = {
            'qd3805_operation_id': op_id,
            'first_row_for_operation': op_id not in seen_ops,
            'plan_id': str(p.get('id') or ''),
            'commune': str(p.get('commune_excel') or ''),
            'plan_text': str(p.get('plan_text') or ''),
            'match_status': str(p.get('match_status') or ''),
            'match_label': str(p.get('match_label') or ''),
            'action_type': str(p.get('action_type') or ''),
            'member_schools': member_names(p),
            'reasons': reasons,
            'categories': categorize(reasons),
            'db_name_suggestions': candidate_suggestions(p, all_schools),
        }
        mapped_block_rows.append(item)
        seen_ops.add(op_id)

    unresolved = []
    for x in registry.get('unresolved_orphans') or []:
        unresolved.append({
            'operation_id': str(x.get('operation_id') or ''),
            'stt': x.get('stt'),
            'commune': str(x.get('commune') or ''),
            'school': str(x.get('school') or ''),
            'source_codes': list(x.get('source_codes') or []),
            'note': x.get('note'),
            'status': str(x.get('status') or ''),
        })

    unique_mapped_block_ops = {x['qd3805_operation_id'] for x in mapped_block_rows if x['qd3805_operation_id']}
    expected = int(preview.get('registry_action_expected_count') or 0)
    done = int(counts.get('DONE') or 0)
    ready = int(counts.get('READY') or 0)
    mapped_block = int(counts.get('BLOCK') or 0)
    unresolved_count = int(preview.get('registry_unresolved_count') or 0)
    effective_block = int(preview.get('effective_block_count') or 0)

    cat_counter = Counter()
    for x in mapped_block_rows:
        if x['first_row_for_operation']:
            for c in x['categories']:
                cat_counter[c] += 1

    report = {
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'project_dir': str(PROJECT_DIR),
        'database_path': str(DATABASE_PATH),
        'database_exists': Path(DATABASE_PATH).exists(),
        'database_size': Path(DATABASE_PATH).stat().st_size if Path(DATABASE_PATH).exists() else None,
        'database_sha256': sha256_file(Path(DATABASE_PATH)) if Path(DATABASE_PATH).exists() else None,
        'school_year_id': yid,
        'school_year': TARGET_YEAR,
        'level_code': TARGET_LEVEL,
        'summary': {
            'qd3805_action_expected': expected,
            'qd3805_action_mapped': int(preview.get('registry_action_mapped_count') or 0),
            'qd3805_keep_expected': int(preview.get('registry_keep_expected_count') or 0),
            'done_unique_operations': done,
            'ready_unique_operations': ready,
            'mapped_block_unique_operations': mapped_block,
            'mapped_operation_equation': done + ready + mapped_block,
            'unresolved_orphans': unresolved_count,
            'effective_items_to_resolve': effective_block,
            'cross_level_special_excluded': int(preview.get('excluded_cross_level_count') or 0),
            'duplicate_mapping_count': int(preview.get('registry_duplicate_mapping_count') or 0),
            'ready_for_execution': bool(preview.get('ready_for_execution')),
        },
        'category_counts_unique_operations': dict(sorted(cat_counter.items())),
        'mapped_block_rows': mapped_block_rows,
        'unresolved_orphans': unresolved,
        'duplicate_mappings': list(registry.get('duplicate_mappings') or []),
        'missing_action_ops': list(registry.get('missing_action_ops') or []),
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    json_path = OUT_DIR / f'bao_cao_phan_loai_44_chan_TH_QD3805_{stamp}.json'
    txt_path = OUT_DIR / f'tom_tat_phan_loai_44_chan_TH_QD3805_{stamp}.txt'
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding='utf-8')

    lines = []
    lines.append('KẾT QUẢ PHÂN LOẠI CHẶN TIỂU HỌC QĐ3805')
    lines.append('=' * 86)
    lines.append(f'QĐ3805 cần tác động: {expected}')
    lines.append(f'Engine ghép được: {preview.get("registry_action_mapped_count")}/{expected}')
    lines.append(f'ĐÃ THỰC HIỆN (operation duy nhất): {done}')
    lines.append(f'ĐẠT - sẽ thực hiện (operation duy nhất): {ready}')
    lines.append(f'CHẶN trong 161 operation đã ghép: {mapped_block}')
    lines.append(f'Kiểm tra phương trình: {done} + {ready} + {mapped_block} = {done + ready + mapped_block}')
    lines.append(f'QĐ3805 chưa xác định ngoài batch: {unresolved_count}')
    lines.append(f'Tổng nội dung cần xử lý để mở nút: {effective_block}')
    lines.append(f'Liên cấp/đặc thù tách riêng: {preview.get("excluded_cross_level_count")}')
    lines.append(f'Trùng ghép operation: {preview.get("registry_duplicate_mapping_count")}')
    lines.append('')
    lines.append('PHÂN NHÓM 43/44 CHẶN ĐÃ GHÉP:')
    for k, v in sorted(cat_counter.items(), key=lambda z: (-z[1], z[0])):
        lines.append(f'  - {k}: {v}')
    lines.append('')
    lines.append('QĐ3805 CHƯA XÁC ĐỊNH:')
    if unresolved:
        for x in unresolved:
            lines.append(f"  - STT {x['stt']} | {x['commune']} | {x['school']} | {x['status']}")
    else:
        lines.append('  - Không có.')
    lines.append('')
    lines.append('DANH SÁCH OPERATION CHẶN ĐÃ GHÉP:')
    for x in mapped_block_rows:
        if not x['first_row_for_operation']:
            continue
        lines.append(f"  - {x['qd3805_operation_id']} | {x['commune']} | {x['plan_text']}")
        for r in x['reasons'][:4]:
            lines.append(f'      * {r}')
    txt_path.write_text('\n'.join(lines), encoding='utf-8')

    print(f'QĐ3805 cần tác động: {expected}')
    print(f'Engine ghép: {preview.get("registry_action_mapped_count")}/{expected}')
    print(f'ĐÃ THỰC HIỆN: {done}')
    print(f'ĐẠT - sẽ thực hiện: {ready}')
    print(f'CHẶN trong 161 operation đã ghép: {mapped_block}')
    print(f'PHƯƠNG TRÌNH: {done} + {ready} + {mapped_block} = {done + ready + mapped_block}')
    print(f'QĐ3805 chưa xác định: {unresolved_count}')
    print(f'TỔNG NỘI DUNG CẦN XỬ LÝ: {effective_block}')
    print(f'LIÊN CẤP/ĐẶC THÙ tách riêng: {preview.get("excluded_cross_level_count")}')
    print(f'TRÙNG GHÉP operation: {preview.get("registry_duplicate_mapping_count")}')
    print('-' * 108)
    print('PHÂN NHÓM CHẶN:')
    for k, v in sorted(cat_counter.items(), key=lambda z: (-z[1], z[0])):
        print(f'  {k}: {v}')
    if unresolved:
        print('-' * 108)
        print('QĐ3805 CHƯA XÁC ĐỊNH:')
        for x in unresolved:
            print(f"  STT {x['stt']} | {x['commune']} | {x['school']} | {x['status']}")
    print('-' * 108)
    print('Database: KHÔNG THAY ĐỔI')
    print(f'Báo cáo JSON: {json_path}')
    print(f'Tóm tắt TXT: {txt_path}')
    print('=' * 108)


if __name__ == '__main__':
    main()
