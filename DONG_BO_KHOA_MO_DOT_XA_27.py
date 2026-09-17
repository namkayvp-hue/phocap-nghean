# -*- coding: utf-8 -*-
from __future__ import annotations
import ast, hashlib, py_compile, re, shutil, sqlite3, sys
from datetime import datetime
from pathlib import Path

ROOT=Path(r"C:\PhoCap")
APP=ROOT/"app"; DB=ROOT/"data"/"phocap.db"
SURVEYS=APP/"routers"/"surveys.py"; TPL=APP/"templates"/"surveys"/"batch_lock.html"
BACKUPS=ROOT/"backups"; EXPORTS=ROOT/"exports"; OUT=EXPORTS/"DONG_BO_KHOA_MO_DOT_XA_27.txt"
MCTX="FIX27_EFFECTIVE_LOCK_CONTEXT"; MLOCK="FIX27_SYNC_COMMUNE_LOCK_ON_BATCH_LOCK"
MUNLOCK="FIX27_SYNC_COMMUNE_UNLOCK_ON_BATCH_UNLOCK"; MTPL="FIX27_EFFECTIVE_LOCK_TEMPLATE"

def sha(p):
    h=hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
    return h.hexdigest()

def log(f,*x):
    s=" ".join(map(str,x)); print(s); f.write(s+"\n"); f.flush()

def dbcheck():
    con=sqlite3.connect(f"file:{DB.as_posix()}?mode=ro",uri=True,timeout=30)
    try:
        integ=con.execute("PRAGMA integrity_check").fetchone()[0]
        fk=con.execute("PRAGMA foreign_key_check").fetchall()
        cols={r[1] for r in con.execute('PRAGMA table_info("survey_commune_execution_states")')}
        row=con.execute("""
        SELECT sb.id,sb.is_locked,COALESCE(st.is_commune_locked,0),COALESCE(st.is_province_locked,0)
        FROM survey_batches sb LEFT JOIN survey_commune_execution_states st ON st.survey_batch_id=sb.id
        WHERE sb.id=114
        """).fetchone()
    finally: con.close()
    need={"survey_batch_id","is_commune_locked","is_province_locked","commune_locked_at","commune_locked_by_user_id","commune_lock_reason","updated_at"}
    if integ!="ok" or fk: raise RuntimeError(f"DB health lỗi integrity={integ} FK={len(fk)}")
    miss=sorted(need-cols)
    if miss: raise RuntimeError("Thiếu cột execution state: "+repr(miss))
    return integ,len(fk),row

def span(text,name):
    tree=ast.parse(text); lines=text.splitlines(keepends=True); offs=[0]; t=0
    for ln in lines: t+=len(ln); offs.append(t)
    nodes=[n for n in ast.walk(tree) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name==name]
    if len(nodes)!=1: raise RuntimeError(f"Cần đúng 1 hàm {name}, thực tế={len(nodes)}")
    n=nodes[0]; return offs[n.lineno-1],offs[n.end_lineno]

def getfn(text,name): a,b=span(text,name); return text[a:b]
def putfn(text,name,fn): a,b=span(text,name); return text[:a]+fn.rstrip()+"\n\n"+text[b:]

def patch_context(src):
    fn=getfn(src,"hien_thi_trang_chot_so_lieu")
    if MCTX in fn: return src,"ALREADY"
    anchor='    lock_data = tao_du_lieu_chot_so_lieu(\n        request=request,\n        db=db,\n        batch=batch,\n    )\n\n'
    if anchor not in fn: raise RuntimeError("Không tìm thấy anchor lock_data")
    block=anchor+'''    # === FIX27_EFFECTIVE_LOCK_CONTEXT_START ===
    _fix27_state = db.execute(
        text("""
            SELECT COALESCE(is_commune_locked,0) AS is_commune_locked,
                   COALESCE(is_province_locked,0) AS is_province_locked
            FROM survey_commune_execution_states
            WHERE survey_batch_id=:batch_id LIMIT 1
        """), {"batch_id": int(batch.id)}
    ).mappings().first()
    _fix27_commune_locked = bool(_fix27_state["is_commune_locked"] if _fix27_state is not None else False)
    _fix27_province_locked = bool(_fix27_state["is_province_locked"] if _fix27_state is not None else False)
    _fix27_school_locked_total = int(db.execute(
        text("""SELECT COUNT(*) FROM survey_school_assignments
                 WHERE survey_batch_id=:batch_id AND COALESCE(is_locked,0)=1"""),
        {"batch_id": int(batch.id)}
    ).scalar() or 0)
    lock_state = {
        "batch_locked": bool(batch.is_locked),
        "commune_locked": _fix27_commune_locked,
        "province_locked": _fix27_province_locked,
        "effective_locked": bool(batch.is_locked or _fix27_commune_locked or _fix27_province_locked),
        "school_locked_total": _fix27_school_locked_total,
    }
    # === FIX27_EFFECTIVE_LOCK_CONTEXT_END ===

'''
    fn=fn.replace(anchor,block,1)
    ca='            "lock_data": lock_data,\n'
    if ca not in fn: raise RuntimeError("Không tìm thấy context lock_data")
    fn=fn.replace(ca,ca+'            "lock_state": lock_state,\n',1)
    return putfn(src,"hien_thi_trang_chot_so_lieu",fn),"PATCHED"

def patch_lock(src):
    fn=getfn(src,"khoa_dot_dieu_tra")
    if MLOCK in fn: return src,"ALREADY"
    if fn.count("    db.commit()\n")!=1: raise RuntimeError("khoa_dot_dieu_tra không có đúng 1 db.commit")
    block='''    # === FIX27_SYNC_COMMUNE_LOCK_ON_BATCH_LOCK_START ===
    _fix27_upd = db.execute(
        text("""UPDATE survey_commune_execution_states
                SET is_commune_locked=1, commune_locked_at=:locked_at,
                    commune_locked_by_user_id=:actor_id, commune_lock_reason=:reason,
                    updated_at=:updated_at
                WHERE survey_batch_id=:batch_id"""),
        {"batch_id":int(batch.id),"locked_at":now,"actor_id":int(user["id"]),"reason":reason,"updated_at":now},
    )
    if int(_fix27_upd.rowcount or 0)==0:
        db.execute(
            text("""INSERT INTO survey_commune_execution_states
                    (survey_batch_id,is_commune_locked,is_province_locked,commune_locked_at,
                     commune_locked_by_user_id,commune_lock_reason,updated_at)
                    VALUES (:batch_id,1,0,:locked_at,:actor_id,:reason,:updated_at)"""),
            {"batch_id":int(batch.id),"locked_at":now,"actor_id":int(user["id"]),"reason":reason,"updated_at":now},
        )
    # === FIX27_SYNC_COMMUNE_LOCK_ON_BATCH_LOCK_END ===

'''
    fn=fn.replace("    db.commit()\n",block+"    db.commit()\n",1)
    return putfn(src,"khoa_dot_dieu_tra",fn),"PATCHED"

def patch_unlock(src):
    fn=getfn(src,"mo_khoa_dot_dieu_tra")
    if MUNLOCK in fn: return src,"ALREADY"
    ea='    errors: list[str] = []\n\n'
    if ea not in fn: raise RuntimeError("Không tìm thấy errors trong mo_khoa_dot_dieu_tra")
    state=ea+'''    _fix27_state = db.execute(
        text("""SELECT COALESCE(is_commune_locked,0) AS is_commune_locked,
                       COALESCE(is_province_locked,0) AS is_province_locked
                FROM survey_commune_execution_states
                WHERE survey_batch_id=:batch_id LIMIT 1"""),
        {"batch_id":int(batch.id)},
    ).mappings().first()
    commune_locked = bool(_fix27_state["is_commune_locked"] if _fix27_state is not None else False)
    province_locked = bool(_fix27_state["is_province_locked"] if _fix27_state is not None else False)

'''
    fn=fn.replace(ea,state,1)
    old='    if not batch.is_locked:\n        errors.append("Đợt điều tra hiện không ở trạng thái khóa.")\n'
    new='''    if province_locked:
        errors.append("Cấp tỉnh đang khóa. Hãy mở khóa cấp tỉnh trước khi mở địa bàn.")
    if not batch.is_locked and not commune_locked:
        errors.append("Đợt và cấp xã hiện đều đang mở cập nhật.")
'''
    if old not in fn: raise RuntimeError("Không tìm thấy kiểm tra not batch.is_locked")
    fn=fn.replace(old,new,1)
    if fn.count("    db.commit()\n")!=1: raise RuntimeError("mo_khoa_dot_dieu_tra không có đúng 1 db.commit")
    block='''    # === FIX27_SYNC_COMMUNE_UNLOCK_ON_BATCH_UNLOCK_START ===
    db.execute(
        text("""UPDATE survey_commune_execution_states
                SET is_commune_locked=0, commune_locked_at=NULL,
                    commune_locked_by_user_id=NULL, commune_lock_reason=NULL,
                    updated_at=:updated_at
                WHERE survey_batch_id=:batch_id AND COALESCE(is_province_locked,0)=0"""),
        {"batch_id":int(batch.id),"updated_at":now},
    )
    # === FIX27_SYNC_COMMUNE_UNLOCK_ON_BATCH_UNLOCK_END ===

'''
    fn=fn.replace("    db.commit()\n",block+"    db.commit()\n",1)
    return putfn(src,"mo_khoa_dot_dieu_tra",fn),"PATCHED"

def patch_tpl(text):
    if MTPL in text: return text,0
    n=text.count("batch.is_locked")
    if n<1: raise RuntimeError("batch_lock.html không còn batch.is_locked để đồng bộ giao diện")
    text=text.replace("batch.is_locked","lock_state.effective_locked")
    if "</body>" not in text: raise RuntimeError("batch_lock.html thiếu </body>")
    return text.replace("</body>",f"<!-- === {MTPL} === -->\n</body>",1),n

def verify(src,tpl):
    ast.parse(src)
    for x in (MCTX,MLOCK,MUNLOCK,'"lock_state": lock_state',"not batch.is_locked and not commune_locked","is_commune_locked=0","is_commune_locked=1"):
        if x not in src: raise RuntimeError("surveys.py thiếu "+x)
    if "batch.is_locked" in tpl: raise RuntimeError("batch_lock.html vẫn còn batch.is_locked")
    if "lock_state.effective_locked" not in tpl or MTPL not in tpl: raise RuntimeError("batch_lock.html chưa dùng khóa hiệu lực")
    from jinja2 import Environment
    Environment().parse(tpl)

def clear_cache():
    for p in APP.rglob("__pycache__"):
        if p.is_dir(): shutil.rmtree(p,ignore_errors=True)

def main():
    EXPORTS.mkdir(parents=True,exist_ok=True); BACKUPS.mkdir(parents=True,exist_ok=True)
    with OUT.open("w",encoding="utf-8-sig",newline="\n") as f:
        log(f,"="*155); log(f,"FIX 27 - ĐỒNG BỘ KHÓA/MỞ ĐỢT VỚI KHÓA CẤP XÃ")
        log(f,"SOURCE ONLY KHI CÀI - KHÔNG GHI DATABASE"); log(f,"="*155)
        for p in (DB,SURVEYS,TPL):
            if not p.exists(): raise RuntimeError(f"Không tìm thấy {p}")
        integ,fk,row=dbcheck(); dbsha=sha(DB)
        log(f,"DB_SHA_BEFORE =",dbsha); log(f,"INTEGRITY =",integ); log(f,"FK_COUNT =",fk)
        log(f,"BATCH_114_STATE_BEFORE_INSTALL =",row)
        src0=SURVEYS.read_text(encoding="utf-8-sig"); tpl0=TPL.read_text(encoding="utf-8-sig")
        for name in ("hien_thi_trang_chot_so_lieu","khoa_dot_dieu_tra","mo_khoa_dot_dieu_tra"): getfn(src0,name)
        stamp=datetime.now().strftime("%Y%m%d_%H%M%S"); bdir=BACKUPS/f"source_truoc_FIX27_{stamp}"
        sb=bdir/SURVEYS.relative_to(ROOT); tb=bdir/TPL.relative_to(ROOT)
        sb.parent.mkdir(parents=True,exist_ok=False); tb.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(SURVEYS,sb); shutil.copy2(TPL,tb); log(f,"SOURCE_BACKUP =",bdir)
        try:
            src,s1=patch_context(src0); src,s2=patch_lock(src); src,s3=patch_unlock(src); tpl,n=patch_tpl(tpl0)
            SURVEYS.write_text(src,encoding="utf-8"); TPL.write_text(tpl,encoding="utf-8")
            py_compile.compile(str(SURVEYS),doraise=True); verify(src,tpl); clear_cache()
            log(f,"PATCH_CONTEXT =",s1); log(f,"PATCH_LOCK =",s2); log(f,"PATCH_UNLOCK =",s3)
            log(f,"TEMPLATE_batch.is_locked_REPLACED =",n); log(f,"PY_COMPILE = PASS"); log(f,"JINJA_VERIFY = PASS")
        except Exception:
            shutil.copy2(sb,SURVEYS); shutil.copy2(tb,TPL); clear_cache(); log(f,"ROLLBACK_SOURCE = PASS"); raise
        if sha(DB)!=dbsha:
            shutil.copy2(sb,SURVEYS); shutil.copy2(tb,TPL); clear_cache(); raise RuntimeError("DB thay đổi trong lúc cài source")
        log(f,"DB_SHA_AFTER =",sha(DB)); log(f,"DATABASE_WRITES_THIS_RUN = 0"); log(f,"FIX27_SUCCESS = YES")
        log(f,"NGUYEN_TAC = trạng thái Chốt số liệu dùng khóa hiệu lực: đợt OR xã OR tỉnh")
        log(f,"LOCK = Chốt & khóa đồng bộ is_commune_locked=1")
        log(f,"UNLOCK = Mở khóa dữ liệu đồng bộ is_commune_locked=0 nếu tỉnh đang mở")
        log(f,"SCHOOL_LOCK = giữ nguyên khóa riêng từng trường"); log(f,"="*155)
    return 0

if __name__=="__main__":
    try: rc=main()
    except Exception as e:
        try:
            EXPORTS.mkdir(parents=True,exist_ok=True)
            with OUT.open("a",encoding="utf-8-sig",newline="\n") as f:
                log(f,""); log(f,"="*155); log(f,"FIX27_SUCCESS = NO"); log(f,"ERROR =",repr(e))
                if DB.exists(): log(f,"DB_SHA_CURRENT =",sha(DB))
                log(f,"DỪNG AN TOÀN."); log(f,"="*155)
        except Exception: print("ERROR =",repr(e))
        rc=1
    raise SystemExit(rc)
