# -*- coding: utf-8 -*-
from __future__ import annotations
import ast, hashlib, py_compile, re, shutil, sqlite3, sys, zipfile
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

ROOT=Path(r'C:\PhoCap'); APP=ROOT/'app'; DB=ROOT/'data'/'phocap.db'
SURVEYS=APP/'routers'/'surveys.py'; HTML=APP/'templates'/'surveys'/'households.html'
BACKUP=ROOT/'backups'; EXPORT=ROOT/'exports'; OUT=EXPORT/'BATCH_THEM_LOC_DOI_TUONG_HO_DAN_25.txt'
MARK='BATCH25_OBJECT_FILTER_BACKEND'; UIMARK='BATCH25_OBJECT_FILTER_UI'

def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()

def log(f,*a):
    s=' '.join(str(x) for x in a); print(s); f.write(s+'\n'); f.flush()

def db_check():
    c=sqlite3.connect(f'file:{DB.as_posix()}?mode=ro',uri=True,timeout=30)
    try:
        integ=c.execute('PRAGMA integrity_check').fetchone()[0]
        fk=c.execute('PRAGMA foreign_key_check').fetchall()
        def cols(t): return {str(r[1]) for r in c.execute(f'PRAGMA table_info("{t}")').fetchall()}
        miss1={'id','household_id','date_of_birth','is_active'}-cols('survey_people')
        miss2={'survey_person_id','school_year_id','disability_status'}-cols('survey_person_year_records')
        miss3={'id','code'}-cols('school_years')
    finally: c.close()
    if integ!='ok' or fk: raise RuntimeError(f'DB health không đạt: integrity={integ}, FK={len(fk)}')
    if miss1 or miss2 or miss3: raise RuntimeError(f'Schema thiếu: people={sorted(miss1)}, year={sorted(miss2)}, school_year={sorted(miss3)}')
    return integ,len(fk)

def span(text,name):
    tree=ast.parse(text); lines=text.splitlines(keepends=True); offs=[0]; n=0
    for line in lines: n+=len(line); offs.append(n)
    nodes=[x for x in ast.walk(tree) if isinstance(x,(ast.FunctionDef,ast.AsyncFunctionDef)) and x.name==name]
    if len(nodes)!=1: raise RuntimeError(f'Cần đúng 1 hàm {name}, có {len(nodes)}')
    node=nodes[0]
    return offs[node.lineno-1],offs[node.end_lineno]

def getfn(text,name):
    a,b=span(text,name); return text[a:b]

def putfn(text,name,fn):
    a,b=span(text,name); return text[:a]+fn.rstrip()+'\n\n'+text[b:]

def patch_helper(src):
    fn=getfn(src,'tao_url_danh_sach_ho')
    if MARK in fn and 'object_filter' in fn: return src,'ALREADY_PRESENT'
    old='    assignment_status: str = "",\n    page_size: int = HOUSEHOLD_PAGE_SIZE,\n'
    if old not in fn: raise RuntimeError('Không tìm thấy chữ ký tao_url_danh_sach_ho')
    fn=fn.replace(old,'    assignment_status: str = "",\n    object_filter: str = "",\n    page_size: int = HOUSEHOLD_PAGE_SIZE,\n',1)
    old2='    if assignment_status:\n        parameters["assignment_status"] = assignment_status\n'
    if old2 not in fn: raise RuntimeError('Không tìm thấy assignment_status URL helper')
    fn=fn.replace(old2,old2+'\n    # BATCH25_OBJECT_FILTER_BACKEND\n    if object_filter:\n        parameters["object_filter"] = object_filter\n',1)
    return putfn(src,'tao_url_danh_sach_ho',fn),'PATCHED'

def patch_route(src):
    fn=getfn(src,'danh_sach_ho_dan')
    if MARK in fn and 'selected_object_filter' in fn: return src,'ALREADY_PRESENT'
    old='    assignment_status: str = "",\n    page_size: int = HOUSEHOLD_PAGE_SIZE,\n'
    if old not in fn: raise RuntimeError('Không tìm thấy chữ ký danh_sach_ho_dan')
    fn=fn.replace(old,'    assignment_status: str = "",\n    object_filter: str = "",\n    page_size: int = HOUSEHOLD_PAGE_SIZE,\n',1)
    norm='    if assignment_status not in {"assigned", "unassigned"}:\n        assignment_status = ""\n'
    block=norm+'''\n    # === BATCH25_OBJECT_FILTER_BACKEND ===\n    object_filter = str(object_filter or "").strip().upper()\n    object_filter_labels = {\n        "": "Tất cả đối tượng",\n        "XMC": "Xóa mù chữ (15-60 tuổi)",\n        "MN": "Mầm non (0-5 tuổi)",\n        "TH": "Tiểu học (6-14 tuổi)",\n        "THCS": "THCS (11-18 tuổi)",\n        "KHUYET_TAT": "Khuyết tật",\n    }\n    if object_filter not in object_filter_labels:\n        object_filter = ""\n    # === END BATCH25_OBJECT_FILTER_BACKEND ===\n'''
    if norm not in fn: raise RuntimeError('Không tìm thấy block chuẩn hóa assignment_status')
    fn=fn.replace(norm,block,1)
    anchor='    total_records = db.scalar(\n'
    filt='''    # === BATCH25_OBJECT_FILTER_BACKEND_APPLY ===\n    if object_filter:\n        sy = db.get(SchoolYear, int(batch.school_year_id))\n        try:\n            ref_year = int(str(sy.code).split("-")[0])\n        except (AttributeError, TypeError, ValueError):\n            ref_year = date.today().year\n\n        age_ranges = {\n            "MN": (0, 5),\n            "TH": (6, 14),\n            "THCS": (11, 18),\n            "XMC": (15, 60),\n        }\n\n        if object_filter in age_ranges:\n            min_age, max_age = age_ranges[object_filter]\n            birth_from = date(ref_year - max_age, 1, 1)\n            birth_to = date(ref_year - min_age, 12, 31)\n            filters.append(\n                Household.people.any(\n                    and_(\n                        SurveyPerson.is_active.is_(True),\n                        SurveyPerson.date_of_birth.is_not(None),\n                        SurveyPerson.date_of_birth >= birth_from,\n                        SurveyPerson.date_of_birth <= birth_to,\n                    )\n                )\n            )\n        elif object_filter == "KHUYET_TAT":\n            disabled_ids = select(SurveyPersonYearRecord.survey_person_id).where(\n                SurveyPersonYearRecord.school_year_id == batch.school_year_id,\n                SurveyPersonYearRecord.disability_status == "CO_KHUYET_TAT",\n            )\n            filters.append(\n                Household.people.any(\n                    and_(\n                        SurveyPerson.is_active.is_(True),\n                        SurveyPerson.id.in_(disabled_ids),\n                    )\n                )\n            )\n    # === END BATCH25_OBJECT_FILTER_BACKEND_APPLY ===\n\n'''
    if anchor not in fn: raise RuntimeError('Không tìm thấy total_records')
    fn=fn.replace(anchor,filt+anchor,1)
    pat=re.compile(r'(?P<i>\s*)assignment_status=assignment_status,\n(?P=i)page_size=page_size,')
    fn,n=pat.subn(lambda m:f'{m.group("i")}assignment_status=assignment_status,\n{m.group("i")}object_filter=object_filter,\n{m.group("i")}page_size=page_size,',fn)
    if n<3: raise RuntimeError(f'Chỉ giữ object_filter ở {n} URL phân trang')
    oldh='        assignment_status,\n    ))\n'
    if oldh not in fn: raise RuntimeError('Không tìm thấy has_filters')
    fn=fn.replace(oldh,'        assignment_status,\n        object_filter,\n    ))\n',1)
    oldc='            "selected_assignment_status": assignment_status,\n            "selected_page_size": page_size,\n'
    if oldc not in fn: raise RuntimeError('Không tìm thấy context selected_assignment_status')
    fn=fn.replace(oldc,'            "selected_assignment_status": assignment_status,\n            "selected_object_filter": object_filter,\n            "object_filter_labels": object_filter_labels,\n            "selected_page_size": page_size,\n',1)
    return putfn(src,'danh_sach_ho_dan',fn),'PATCHED'

def patch_html(text):
    if UIMARK in text: return text,'ALREADY_PRESENT'
    base=text.find('Tìm đúng hộ cần xử lý')
    if base<0: raise RuntimeError('Không tìm thấy Tìm đúng hộ cần xử lý')
    m=re.search(r'<label\b[^>]*for=["\']page_size["\'][^>]*>',text[base:],re.I)
    if not m: raise RuntimeError('Không tìm thấy label page_size')
    pos=base+m.start(); ds=text.rfind('<div',base,pos); de=text.find('>',ds)
    if ds<0 or de<0: raise RuntimeError('Không xác định được div page_size')
    open_div=text[ds:de+1]
    part=text[pos:]
    sm=re.search(r'<select\b([^>]*)\bname=["\']page_size["\']([^>]*)>',part,re.I)
    cls=''
    if sm:
        cm=re.search(r'class=["\']([^"\']+)["\']',sm.group(0),re.I)
        if cm: cls=f' class="{cm.group(1)}"'
    block=f'''                {{# === BATCH25_OBJECT_FILTER_UI === #}}\n                {open_div}\n                    <label for="object_filter">Đối tượng</label>\n                    <select id="object_filter" name="object_filter"{cls}>\n                        {{% for code, label in object_filter_labels.items() %}}\n                            <option value="{{{{ code }}}}" {{% if selected_object_filter == code %}}selected{{% endif %}}>\n                                {{% if code %}}{{{{ label }}}}{{% else %}}-- Tất cả đối tượng --{{% endif %}}\n                            </option>\n                        {{% endfor %}}\n                    </select>\n                </div>\n                {{# === END BATCH25_OBJECT_FILTER_UI === #}}\n\n'''
    return text[:ds]+block+text[ds:],'PATCHED'

def verify():
    src=SURVEYS.read_text(encoding='utf-8'); html=HTML.read_text(encoding='utf-8'); ast.parse(src)
    for x in [MARK,'object_filter: str = ""','"XMC": "Xóa mù chữ (15-60 tuổi)"','"KHUYET_TAT": "Khuyết tật"','SurveyPersonYearRecord.disability_status','"selected_object_filter": object_filter']:
        if x not in src: raise RuntimeError('surveys.py thiếu '+x)
    for x in [UIMARK,'name="object_filter"','object_filter_labels.items()','selected_object_filter']:
        if x not in html: raise RuntimeError('households.html thiếu '+x)
    from jinja2 import Environment; Environment().parse(html)

def clear_cache():
    for p in APP.rglob('__pycache__'):
        if p.is_dir(): shutil.rmtree(p,ignore_errors=True)

def main():
    EXPORT.mkdir(parents=True,exist_ok=True); BACKUP.mkdir(parents=True,exist_ok=True)
    with OUT.open('w',encoding='utf-8-sig',newline='\n') as f:
        log(f,'='*150); log(f,"BATCH 25 - THÊM LỌC ĐỐI TƯỢNG: XMC / MN / TH / THCS / KHUYẾT TẬT"); log(f,'='*150)
        if not DB.exists() or not SURVEYS.exists() or not HTML.exists(): raise RuntimeError('Thiếu DB/source')
        integ,fk=db_check(); dbsha=sha(DB); log(f,'DB_SHA_BEFORE =',dbsha); log(f,'INTEGRITY =',integ); log(f,'FK =',fk)
        s0=SURVEYS.read_text(encoding='utf-8-sig'); h0=HTML.read_text(encoding='utf-8-sig')
        for x in ['def tao_url_danh_sach_ho(','def danh_sach_ho_dan(','tao_bo_loc_phieu_theo_nguoi_dung','SurveyPersonYearRecord']:
            if x not in s0: raise RuntimeError('surveys.py thiếu nền: '+x)
        for x in ['Tìm đúng hộ cần xử lý','name="page_size"','Tình trạng phân công']:
            if x not in h0: raise RuntimeError('households.html thiếu nền: '+x)
        stamp=datetime.now().strftime('%Y%m%d_%H%M%S'); broot=BACKUP/f'source_truoc_BATCH25_{stamp}'; broot.mkdir(parents=True)
        sb=broot/SURVEYS.relative_to(ROOT); hb=broot/HTML.relative_to(ROOT); sb.parent.mkdir(parents=True,exist_ok=True); hb.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(SURVEYS,sb); shutil.copy2(HTML,hb)
        log(f,'SOURCE_BACKUP_DIR =',broot)
        try:
            s1,a=patch_helper(s0); s2,b=patch_route(s1); h1,c=patch_html(h0)
            SURVEYS.write_text(s2,encoding='utf-8'); HTML.write_text(h1,encoding='utf-8'); py_compile.compile(str(SURVEYS),doraise=True); verify(); clear_cache()
            log(f,'PATCH URL =',a); log(f,'PATCH ROUTE =',b); log(f,'PATCH UI =',c); log(f,'PY_COMPILE = PASS'); log(f,'SOURCE_VERIFY = PASS')
        except Exception:
            shutil.copy2(sb,SURVEYS); shutil.copy2(hb,HTML); clear_cache(); log(f,'ROLLBACK_SOURCE = PASS'); raise
        if sha(DB)!=dbsha:
            shutil.copy2(sb,SURVEYS); shutil.copy2(hb,HTML); clear_cache(); raise RuntimeError('DB thay đổi trong khi cài source')
        log(f,'DB_SHA_AFTER =',sha(DB)); log(f,'DATABASE_WRITES_THIS_RUN = 0'); log(f,'BATCH_25_SUCCESS = YES')
        log(f,'FILTER = Tất cả | Xóa mù chữ | Mầm non | Tiểu học | THCS | Khuyết tật')
        log(f,'TUOI = MN 0-5; TH 6-14; THCS 11-18; XMC 15-60 theo năm đầu năm học')
        log(f,'PHAM_VI = Giữ nguyên scope Sở/Xã/Trường/GV hiện có; chỉ lọc bên trong phạm vi được xem')
        log(f,'='*150)
    return 0

if __name__=='__main__':
    try: rc=main()
    except Exception as e:
        try:
            EXPORT.mkdir(parents=True,exist_ok=True)
            with OUT.open('a',encoding='utf-8-sig',newline='\n') as f:
                log(f,''); log(f,'='*150); log(f,'BATCH_25_SUCCESS = NO'); log(f,'ERROR =',repr(e)); log(f,'DỪNG AN TOÀN.'); log(f,'='*150)
        except Exception: print('ERROR =',repr(e))
        rc=1
    raise SystemExit(rc)
