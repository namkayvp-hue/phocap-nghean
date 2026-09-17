# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import inspect
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(r"C:\PhoCap")
DB = ROOT / "data" / "phocap.db"
BACKUP_DIR = ROOT / "backups"
EXPORT_DIR = ROOT / "exports"
OUT = EXPORT_DIR / "BATCH_DU_LIEU_HAU_SAP_NHAP_TOAN_TINH_07B.txt"

# Batch 07 trước dừng an toàn, DB không đổi.
EXPECTED_DB_SHA = "fd20f8150c0dc83855b00cb6da3ed5ea7f8fd11d4ab461506836f5446591738d"

CURRENT_YEAR_ID = 2
TARGET_BATCH_ID = 114
TARGET_SCHOOL_ID = 1606

SCHOOL_REASON = (
    "Batch 07B - Khóa trường theo đúng route hiện hành sau khi source helper "
    "xác nhận 100% phiếu của trường đã hoàn thành."
)
COMMUNE_REASON = (
    "Batch 07B - Khóa xã theo đúng route hiện hành sau khi trường có phiếu "
    "đã được khóa/xác nhận hoàn thành và toàn bộ phiếu địa bàn đã hoàn thành."
)

LOG = None

def log(*args):
    s = " ".join(str(x) for x in args)
    print(s)
    if LOG:
        LOG.write(s + "\n")
        LOG.flush()

def fail(msg):
    raise RuntimeError(msg)

def sha256_file(path: Path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()

def make_backup():
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = BACKUP_DIR / f"backup_truoc_BATCH_DU_LIEU_07B_{ts}.db"

    src = sqlite3.connect(str(DB), timeout=60)
    dst = sqlite3.connect(str(path), timeout=60)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()

    ro = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=30)
    try:
        integ = ro.execute("PRAGMA integrity_check").fetchone()[0]
        fk = ro.execute("PRAGMA foreign_key_check").fetchall()
    finally:
        ro.close()

    if integ != "ok" or fk:
        fail(f"Backup không đạt integrity={integ}, fk={len(fk)}")
    return path

def sqlite_row(conn, sql, params=()):
    cur = conn.execute(sql, params)
    r = cur.fetchone()
    if r is None:
        return None
    return dict(zip([d[0] for d in cur.description], r))

def active_commune_actor(conn):
    rows = conn.execute(
        """
        SELECT
            u.id,
            u.username,
            u.full_name,
            u.commune_id,
            u.school_id,
            u.is_active,
            r.code AS role_code,
            r.name AS role_name
        FROM users u
        JOIN roles r ON r.id=u.role_id
        WHERE u.is_active=1
          AND u.commune_id=?
          AND UPPER(r.code)='XA'
        ORDER BY u.id
        """,
        (TARGET_BATCH_ID,)
    ).fetchall()

    names = [d[0] for d in conn.execute(
        """
        SELECT
            u.id,u.username,u.full_name,u.commune_id,u.school_id,u.is_active,
            r.code AS role_code,r.name AS role_name
        FROM users u
        JOIN roles r ON r.id=u.role_id
        WHERE 1=0
        """
    ).description]

    actors = [dict(zip(names, r)) for r in rows]
    log("ACTIVE_XA_ACTORS =", json.dumps(actors, ensure_ascii=False, default=str))

    if len(actors) != 1:
        fail(
            f"Cần đúng 1 tài khoản XA active cho commune 114, "
            f"thực tế={len(actors)}"
        )

    a = actors[0]
    return {
        "id": int(a["id"]),
        "username": str(a["username"] or ""),
        "full_name": str(a["full_name"] or a["username"] or ""),
        "role_code": str(a["role_code"] or ""),
        "role_name": str(a["role_name"] or ""),
        "commune_id": int(a["commune_id"]),
        "school_id": a["school_id"],
        "is_active": int(a["is_active"] or 0),
    }

class DummyRequest:
    """
    Đủ dữ liệu cho lay_nguoi_dung(request) của dự án.
    Có cả scope và state để không phụ thuộc cách helper đang đọc auth_user.
    """
    def __init__(self, actor):
        self.scope = {"auth_user": actor}
        self.state = SimpleNamespace(auth_user=actor)
        self.session = {}

def response_location(resp):
    try:
        return resp.headers.get("location")
    except Exception:
        return None

def main():
    global LOG
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    LOG = OUT.open("w", encoding="utf-8-sig", newline="\n")

    log("="*160)
    log("BATCH DỮ LIỆU HẬU SÁP NHẬP TOÀN TỈNH 07B")
    log("DÙNG ĐÚNG TÀI KHOẢN XÃ ACTIVE + GỌI TRỰC TIẾP ROUTE HIỆN HÀNH")
    log("MỤC TIÊU: KHÓA TRƯỜNG 1606; SAU ĐÓ CHỈ KHÓA XÃ 114 NẾU CHÍNH ROUTE KHOA_XA CHẤP NHẬN")
    log("KHÔNG GỌI KHÓA SỞ")
    log("="*160)

    wal = DB.parent / "phocap.db-wal"
    journal = DB.parent / "phocap.db-journal"
    wal_size = wal.stat().st_size if wal.exists() else 0
    journal_size = journal.stat().st_size if journal.exists() else 0
    log("WAL_SIZE =", wal_size)
    log("JOURNAL_SIZE =", journal_size)
    if wal_size or journal_size:
        fail("WAL/JOURNAL khác 0")

    sha = sha256_file(DB)
    log("DB_SHA_BEFORE =", sha)
    log("EXPECTED_DB_SHA =", EXPECTED_DB_SHA)
    if sha != EXPECTED_DB_SHA:
        fail("DB SHA khác nền Batch 07 dừng an toàn")

    ro = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True, timeout=30)
    try:
        integ = ro.execute("PRAGMA integrity_check").fetchone()[0]
        fk = ro.execute("PRAGMA foreign_key_check").fetchall()
        log("INTEGRITY_BEFORE =", integ)
        log("FK_BEFORE =", len(fk))
        if integ != "ok" or fk:
            fail("Database health không đạt")

        actor = active_commune_actor(ro)

        assignment_before = sqlite_row(
            ro,
            """
            SELECT a.*,b.school_year_id,b.commune_id AS batch_commune_id,
                   b.status AS batch_status,b.is_locked AS batch_locked,
                   COALESCE(es.is_commune_locked,0) AS commune_locked,
                   COALESCE(es.is_province_locked,0) AS province_locked,
                   s.code AS school_code,s.name AS school_name,s.is_active AS school_active
            FROM survey_school_assignments a
            JOIN survey_batches b ON b.id=a.survey_batch_id
            JOIN schools s ON s.id=a.school_id
            LEFT JOIN survey_commune_execution_states es
                   ON es.survey_batch_id=b.id
            WHERE a.survey_batch_id=? AND a.school_id=?
            """,
            (TARGET_BATCH_ID, TARGET_SCHOOL_ID)
        )
        log("ASSIGNMENT_BEFORE =", json.dumps(
            assignment_before, ensure_ascii=False, default=str
        ))

        if not assignment_before:
            fail("Không tìm thấy assignment batch114-school1606")
        if int(assignment_before["school_year_id"]) != CURRENT_YEAR_ID:
            fail("Sai school_year_id")
        if str(assignment_before["status"]) != "DA_GUI_XA":
            fail("Assignment không còn DA_GUI_XA")
        if int(assignment_before["is_locked"] or 0) != 0:
            fail("Assignment đã khóa")
        if int(assignment_before["batch_locked"] or 0) != 0:
            fail("Batch đã khóa")
        if int(assignment_before["commune_locked"] or 0) != 0:
            fail("Xã đã khóa")
        if int(assignment_before["province_locked"] or 0) != 0:
            fail("Sở đã khóa")
        if int(assignment_before["school_active"] or 0) != 1:
            fail("Trường 1606 không active")
    finally:
        ro.close()

    import app.routers.survey_school_workflow as wf
    from app.database import engine
    from sqlalchemy.orm import Session

    # Ghi lại source route đang dùng để biết script đang gọi đúng logic hiện hành.
    source_school = inspect.getsource(wf.khoa_truong)
    source_commune = inspect.getsource(wf.khoa_toan_xa)
    source_user = inspect.getsource(wf.lay_nguoi_dung)

    log("KHOA_TRUONG_SOURCE_SHA256 =", hashlib.sha256(source_school.encode("utf-8")).hexdigest())
    log("KHOA_XA_SOURCE_SHA256 =", hashlib.sha256(source_commune.encode("utf-8")).hexdigest())
    log("LAY_NGUOI_DUNG_SOURCE_SHA256 =", hashlib.sha256(source_user.encode("utf-8")).hexdigest())

    # Preview bằng chính source helper và quyền hiện hành.
    with Session(engine) as db:
        batch = wf.lay_dot(db, TARGET_BATCH_ID)
        if batch is None:
            fail("wf.lay_dot không tìm thấy batch 114")

        if not wf.co_quyen_quan_ly_xa(user=actor, batch=batch):
            fail("Tài khoản XA active không được source hiện hành xác nhận quyền quản lý xã")

        counts = wf.dem_phieu_cua_truong(
            db,
            batch_id=TARGET_BATCH_ID,
            school_id=TARGET_SCHOOL_ID,
        )
        log("SOURCE_COUNTS_PREVIEW =", json.dumps(
            counts, ensure_ascii=False, default=str
        ))

        form_total = int(counts.get("form_total") or 0)
        completed_total = int(counts.get("completed_total") or 0)
        if form_total <= 0 or completed_total != form_total:
            fail(
                f"Trường chưa đạt điều kiện route: "
                f"{completed_total}/{form_total}"
            )

    backup = make_backup()
    log("BACKUP =", backup)
    log("BACKUP_SHA =", sha256_file(backup))

    request = DummyRequest(actor)

    # ============================================================
    # 1) GỌI TRỰC TIẾP ROUTE KHÓA TRƯỜNG HIỆN HÀNH
    # ============================================================
    with Session(engine) as db:
        result = wf.khoa_truong(
            request=request,
            batch_id=TARGET_BATCH_ID,
            school_id=TARGET_SCHOOL_ID,
            reason=SCHOOL_REASON,
            db=db,
        )
        school_route_location = response_location(result)
        log("KHOA_TRUONG_ROUTE_LOCATION =", school_route_location)

    # Post-check ngay sau route trường.
    ro = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True, timeout=30)
    try:
        assignment_after_school = sqlite_row(
            ro,
            "SELECT * FROM survey_school_assignments "
            "WHERE survey_batch_id=? AND school_id=?",
            (TARGET_BATCH_ID, TARGET_SCHOOL_ID)
        )
        log("ASSIGNMENT_AFTER_SCHOOL_ROUTE =", json.dumps(
            assignment_after_school, ensure_ascii=False, default=str
        ))

        if (
            not assignment_after_school
            or int(assignment_after_school["is_locked"] or 0) != 1
            or str(assignment_after_school["status"]) != "DA_HOAN_THANH"
            or int(assignment_after_school["locked_by_user_id"] or 0) != actor["id"]
        ):
            fail("Route khóa trường không tạo đúng trạng thái mong đợi")

        school_log = sqlite_row(
            ro,
            """
            SELECT *
            FROM survey_execution_workflow_logs
            WHERE survey_batch_id=?
              AND school_id=?
              AND action='KHOA_TRUONG'
            ORDER BY id DESC
            LIMIT 1
            """,
            (TARGET_BATCH_ID, TARGET_SCHOOL_ID)
        )
        log("LATEST_KHOA_TRUONG_LOG =", json.dumps(
            school_log, ensure_ascii=False, default=str
        ))
        if not school_log:
            fail("Không có workflow log KHOA_TRUONG")
    finally:
        ro.close()

    # ============================================================
    # 2) GỌI TRỰC TIẾP ROUTE KHÓA XÃ.
    #    CHÍNH ROUTE QUYẾT ĐỊNH CÓ ĐỦ ĐIỀU KIỆN HAY KHÔNG.
    # ============================================================
    with Session(engine) as db:
        result2 = wf.khoa_toan_xa(
            request=request,
            batch_id=TARGET_BATCH_ID,
            reason=COMMUNE_REASON,
            db=db,
        )
        commune_route_location = response_location(result2)
        log("KHOA_XA_ROUTE_LOCATION =", commune_route_location)

    # Post verify chung.
    ro = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True, timeout=30)
    try:
        integ = ro.execute("PRAGMA integrity_check").fetchone()[0]
        fk = ro.execute("PRAGMA foreign_key_check").fetchall()

        state = sqlite_row(
            ro,
            """
            SELECT b.id,b.school_year_id,b.commune_id,b.status,b.is_locked,
                   b.status_before_lock,
                   es.is_commune_locked,es.is_province_locked,
                   es.commune_locked_at,es.commune_locked_by_user_id,
                   es.commune_lock_reason
            FROM survey_batches b
            JOIN survey_commune_execution_states es
              ON es.survey_batch_id=b.id
            WHERE b.id=?
            """,
            (TARGET_BATCH_ID,)
        )

        commune_log = sqlite_row(
            ro,
            """
            SELECT *
            FROM survey_execution_workflow_logs
            WHERE survey_batch_id=?
              AND action='KHOA_XA'
            ORDER BY id DESC LIMIT 1
            """,
            (TARGET_BATCH_ID,)
        )

        log("\n" + "="*160)
        log("POST VERIFY BATCH 07B")
        log("="*160)
        log("INTEGRITY_AFTER =", integ)
        log("FK_AFTER =", len(fk))
        log("BATCH114_STATE_AFTER =", json.dumps(
            state, ensure_ascii=False, default=str
        ))
        log("LATEST_KHOA_XA_LOG =", json.dumps(
            commune_log, ensure_ascii=False, default=str
        ))
        log("DB_SHA_AFTER =", sha256_file(DB))

        if integ != "ok" or fk:
            fail("Database sau route không đạt")

        commune_locked = bool(int(state["is_commune_locked"] or 0))
        province_locked = bool(int(state["is_province_locked"] or 0))

        if province_locked:
            fail("Batch 07B không được phép khóa Sở nhưng is_province_locked=1")

        log("SCHOOL_LOCK_COMMITTED = YES")
        log("COMMUNE_LOCK_COMMITTED =", "YES" if commune_locked else "NO")
        log("PROVINCE_LOCK_COMMITTED = NO")
        log("BATCH_07B_SUCCESS = YES")

        if commune_locked:
            log(
                "NEXT_STAGE = Xã 114 đã được chính route hiện hành khóa thành công. "
                "129 xã chưa có dữ liệu giữ nguyên; chưa thể khóa Sở toàn tỉnh."
            )
        else:
            log(
                "NEXT_STAGE = Trường đã khóa; route khóa xã chưa chấp nhận. "
                "Dùng KHOA_XA_ROUTE_LOCATION + trạng thái log để xử lý đúng điều kiện còn thiếu."
            )

        log("="*160)
        return 0
    finally:
        ro.close()
        if LOG:
            LOG.close()

if __name__ == "__main__":
    try:
        code = main()
    except Exception as exc:
        try:
            log("\n" + "="*160)
            log("BATCH_07B_SUCCESS = NO")
            log("ERROR =", repr(exc))
            if DB.exists():
                log("DB_SHA_CURRENT =", sha256_file(DB))
            log("DỪNG AN TOÀN.")
            log("="*160)
        finally:
            if LOG and not LOG.closed:
                LOG.close()
        code = 1
    sys.exit(code)
