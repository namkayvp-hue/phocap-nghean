# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
import hashlib
import inspect
import json
import sqlite3
import sys
import textwrap
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(r"C:\PhoCap")
DB = ROOT / "data" / "phocap.db"
BACKUP_DIR = ROOT / "backups"
EXPORT_DIR = ROOT / "exports"
OUT = EXPORT_DIR / "BATCH_DU_LIEU_HAU_SAP_NHAP_TOAN_TINH_07.txt"

# Nền sau Batch 05; Batch 06 chỉ đọc nên SHA không đổi.
EXPECTED_DB_SHA = "fd20f8150c0dc83855b00cb6da3ed5ea7f8fd11d4ab461506836f5446591738d"

CURRENT_YEAR_ID = 2
TARGET_BATCH_ID = 114

LOCK_REASON = (
    "Batch 07 - Khóa trường sau khi kiểm tra đúng quy tắc hiện hành: "
    "trường có phiếu và 100% phiếu được tính cho trường đã hoàn thành."
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

def qi(name):
    return '"' + str(name).replace('"', '""') + '"'

def sha256_file(path: Path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()

def table_info(conn, table):
    return conn.execute(f"PRAGMA table_info({qi(table)})").fetchall()

def cols(conn, table):
    return [r[1] for r in table_info(conn, table)]

def row_dict(cur, row):
    return dict(zip([d[0] for d in cur.description], row))

def one_dict(conn, sql, params=()):
    cur = conn.execute(sql, params)
    row = cur.fetchone()
    return row_dict(cur, row) if row else None

def all_dict(conn, sql, params=()):
    cur = conn.execute(sql, params)
    names = [d[0] for d in cur.description]
    return [dict(zip(names, r)) for r in cur.fetchall()]

def make_backup():
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = BACKUP_DIR / f"backup_truoc_BATCH_DU_LIEU_07_{ts}.db"

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

def actor_snapshot(conn, user_id):
    u = one_dict(conn, "SELECT * FROM users WHERE id=?", (user_id,))
    if not u:
        fail(f"Không tìm thấy actor user_id={user_id}")

    role_code = ""
    role_name = ""
    if u.get("role_id") is not None:
        role = one_dict(conn, "SELECT * FROM roles WHERE id=?", (u["role_id"],))
        if role:
            role_code = str(role.get("code") or "")
            role_name = str(role.get("name") or "")

    full_name = str(
        u.get("full_name")
        or u.get("name")
        or u.get("username")
        or f"user_{user_id}"
    )
    return {
        "id": int(user_id),
        "username": str(u.get("username") or ""),
        "full_name": full_name,
        "role_code": role_code,
        "role_name": role_name,
        "commune_id": u.get("commune_id"),
        "school_id": u.get("school_id"),
        "is_active": int(u.get("is_active") or 0),
    }

def find_counts_helper():
    """
    Đọc đúng source đang chạy trong C:\PhoCap.
    Chỉ chấp nhận helper READ-ONLY được gán vào biến `counts`
    bên trong route khoa_truong().
    """
    import app.routers.survey_school_workflow as wf

    src = textwrap.dedent(inspect.getsource(wf.khoa_truong))
    log("KHOA_TRUONG_SOURCE_SHA256 =", hashlib.sha256(src.encode("utf-8")).hexdigest())
    log("KHOA_TRUONG_SOURCE_START")
    for line in src.splitlines():
        log("SRC", line)
    log("KHOA_TRUONG_SOURCE_END")

    tree = ast.parse(src)
    helper_name = None

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if "counts" not in targets or not isinstance(node.value, ast.Call):
                continue
            func = node.value.func
            if isinstance(func, ast.Name):
                helper_name = func.id
                break
            if isinstance(func, ast.Attribute):
                helper_name = func.attr
                break

    if not helper_name:
        # Fallback nhẹ nếu AST không bắt được vì source thay đổi.
        import re
        m = re.search(r"\bcounts\s*=\s*([A-Za-z_][A-Za-z0-9_]*)\s*\(", src)
        if m:
            helper_name = m.group(1)

    if not helper_name:
        fail("Không xác định được helper đếm tiến độ trường từ source hiện hành")

    helper = getattr(wf, helper_name, None)
    if helper is None or not callable(helper):
        fail(f"Helper {helper_name} không callable")

    helper_src = textwrap.dedent(inspect.getsource(helper))
    low = helper_src.lower()

    # Gate chống gọi nhầm helper có ghi DB.
    dangerous = [
        ".commit(", ".rollback(", ".flush(", ".add(", ".delete(",
        " insert ", " update ", " delete ", "merge("
    ]
    if any(x in low for x in dangerous):
        fail(f"Helper {helper_name} có dấu hiệu ghi DB; dừng an toàn")

    log("COUNTS_HELPER_NAME =", helper_name)
    log("COUNTS_HELPER_SOURCE_SHA256 =", hashlib.sha256(helper_src.encode("utf-8")).hexdigest())
    log("COUNTS_HELPER_SOURCE_START")
    for line in helper_src.splitlines():
        log("HELPER", line)
    log("COUNTS_HELPER_SOURCE_END")

    return wf, helper_name, helper

def call_counts_helper(helper, batch_id, school_id):
    from sqlalchemy.orm import Session
    from app.database import engine

    sig = inspect.signature(helper)
    kwargs = {}

    with Session(engine) as db:
        for name, param in sig.parameters.items():
            lname = name.lower()
            if lname in {"db", "session"}:
                kwargs[name] = db
            elif lname in {"batch_id", "survey_batch_id"}:
                kwargs[name] = batch_id
            elif lname in {"school_id", "truong_id"}:
                kwargs[name] = school_id
            elif param.default is inspect._empty:
                fail(
                    f"Không biết cấp tham số bắt buộc {name} "
                    f"cho helper {helper.__name__}{sig}"
                )

        result = helper(**kwargs)

        if isinstance(result, dict):
            return dict(result)
        if hasattr(result, "_mapping"):
            return dict(result._mapping)
        fail(f"Helper trả kiểu không hỗ trợ: {type(result)!r}")

def candidate_assignments(conn):
    return all_dict(
        conn,
        """
        SELECT
            a.*,
            b.school_year_id,
            b.commune_id AS batch_commune_id,
            b.status AS batch_status,
            b.is_locked AS batch_is_locked,
            s.code AS school_code,
            s.name AS school_name,
            s.commune_id AS school_commune_id,
            s.is_active AS school_is_active,
            COALESCE(es.is_commune_locked,0) AS commune_locked,
            COALESCE(es.is_province_locked,0) AS province_locked
        FROM survey_school_assignments a
        JOIN survey_batches b ON b.id=a.survey_batch_id
        JOIN schools s ON s.id=a.school_id
        LEFT JOIN survey_commune_execution_states es
               ON es.survey_batch_id=b.id
        WHERE a.survey_batch_id=?
          AND a.status='DA_GUI_XA'
          AND COALESCE(a.is_locked,0)=0
        ORDER BY a.id
        """,
        (TARGET_BATCH_ID,)
    )

def full_batch_safety(conn, batch_id):
    row = one_dict(
        conn,
        """
        SELECT b.id,b.school_year_id,b.commune_id,b.status,b.is_locked,
               COALESCE(es.is_commune_locked,0) AS commune_locked,
               COALESCE(es.is_province_locked,0) AS province_locked
        FROM survey_batches b
        LEFT JOIN survey_commune_execution_states es
               ON es.survey_batch_id=b.id
        WHERE b.id=?
        """,
        (batch_id,)
    )
    if not row:
        fail(f"Không tìm thấy survey_batch {batch_id}")
    if int(row["school_year_id"]) != CURRENT_YEAR_ID:
        fail("Batch không thuộc school_year_id=2")
    if int(row["is_locked"] or 0) != 0:
        fail("Batch đã khóa")
    if int(row["commune_locked"] or 0) != 0:
        fail("Xã đã khóa")
    if int(row["province_locked"] or 0) != 0:
        fail("Sở đã khóa")
    return row

def insert_workflow_log(conn, *, batch_id, school_id, actor, form_total, completed_total):
    c = cols(conn, "survey_execution_workflow_logs")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")

    values = {
        "survey_batch_id": batch_id,
        "school_id": school_id,
        "action": "KHOA_TRUONG",
        "actor_user_id": actor["id"],
        "actor_name_snapshot": actor["full_name"],
        "actor_role_snapshot": actor["role_name"] or actor["role_code"],
        "reason": LOCK_REASON,
        "form_total": int(form_total),
        "completed_form_total": int(completed_total),
        "created_at": now,
    }

    use_cols = [x for x in values if x in c]
    sql = (
        f"INSERT INTO survey_execution_workflow_logs "
        f"({', '.join(qi(x) for x in use_cols)}) "
        f"VALUES ({', '.join('?' for _ in use_cols)})"
    )
    conn.execute(sql, [values[x] for x in use_cols])

def main():
    global LOG
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    LOG = OUT.open("w", encoding="utf-8-sig", newline="\n")

    log("=" * 160)
    log("BATCH DỮ LIỆU HẬU SÁP NHẬP TOÀN TỈNH 07")
    log("GHI THẬT CHỈ NHỮNG KHÓA TRƯỜNG ĐỦ ĐIỀU KIỆN THEO HELPER SOURCE CODE HIỆN HÀNH")
    log("KHÔNG TỰ KHÓA XÃ / KHÔNG TỰ KHÓA SỞ")
    log("=" * 160)

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
        fail("DB SHA khác nền Batch 05/06")

    # DB health trước.
    ro = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True, timeout=30)
    try:
        integ = ro.execute("PRAGMA integrity_check").fetchone()[0]
        fk = ro.execute("PRAGMA foreign_key_check").fetchall()
        log("INTEGRITY_BEFORE =", integ)
        log("FK_BEFORE =", len(fk))
        if integ != "ok" or fk:
            fail("Database health không đạt")
    finally:
        ro.close()

    # Đọc đúng source đang chạy và xác định helper tiến độ trường.
    wf, helper_name, helper = find_counts_helper()

    # Rà candidate trước khi backup/write.
    ro = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True, timeout=30)
    try:
        batch_state = full_batch_safety(ro, TARGET_BATCH_ID)
        candidates = candidate_assignments(ro)
        log("TARGET_BATCH_STATE =", json.dumps(batch_state, ensure_ascii=False, default=str))
        log("CANDIDATE_ASSIGNMENTS =", json.dumps(candidates, ensure_ascii=False, default=str))

        if not candidates:
            log("NO_WRITE_REASON = Không có assignment DA_GUI_XA chưa khóa.")
            log("BATCH_07_SUCCESS = YES_NO_WRITE")
            return 0

        # Hiện dữ liệu test chỉ nên có đúng 1 candidate.
        if len(candidates) != 1:
            fail(f"Kỳ vọng đúng 1 candidate ở batch 114, thực tế {len(candidates)}")

        c = candidates[0]

        if int(c["school_year_id"]) != CURRENT_YEAR_ID:
            fail("Candidate không thuộc 2026-2027")
        if int(c["batch_is_locked"] or 0) != 0:
            fail("Batch đang khóa")
        if int(c["commune_locked"] or 0) != 0 or int(c["province_locked"] or 0) != 0:
            fail("Xã/Sở đang khóa")
        if int(c["school_is_active"] or 0) != 1:
            fail("Trường candidate không active")

        counts = call_counts_helper(
            helper,
            int(c["survey_batch_id"]),
            int(c["school_id"]),
        )
        log("SOURCE_HELPER_COUNTS =", json.dumps(counts, ensure_ascii=False, default=str))

        form_total = int(counts.get("form_total") or 0)
        completed_total = int(counts.get("completed_total") or 0)

        if form_total <= 0:
            fail("Source helper xác nhận trường không có phiếu")
        if completed_total != form_total:
            fail(
                f"Source helper chưa đủ 100%: "
                f"{completed_total}/{form_total}"
            )

        # Actor phải là đúng người đã giao assignment và đang active.
        actor_id = c.get("assigned_by_user_id")
        if actor_id is None:
            fail("Assignment không có assigned_by_user_id để làm actor hợp lệ")

        actor = actor_snapshot(ro, int(actor_id))
        log("ACTOR =", json.dumps(actor, ensure_ascii=False, default=str))

        if actor["is_active"] != 1:
            fail("Actor đã bị khóa")
        if actor["role_code"].upper() not in {"XA", "SO", "ADMIN", "SOGDDT"}:
            fail(f"Actor role không phù hợp để khóa trường: {actor['role_code']}")
        if actor["role_code"].upper() == "XA":
            if actor["commune_id"] is None:
                fail("Actor XA không có commune_id")
            if int(actor["commune_id"]) != int(c["batch_commune_id"]):
                fail("Actor XA không đúng xã của batch")

        pre_log_count = ro.execute(
            "SELECT COUNT(*) FROM survey_execution_workflow_logs"
        ).fetchone()[0]
        pre_assignment = one_dict(
            ro,
            "SELECT * FROM survey_school_assignments WHERE id=?",
            (c["id"],)
        )
    finally:
        ro.close()

    # Backup sau khi toàn bộ gate đọc đã PASS.
    backup = make_backup()
    log("BACKUP =", backup)
    log("BACKUP_SHA =", sha256_file(backup))

    conn = sqlite3.connect(str(DB), timeout=60)
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        conn.execute("BEGIN IMMEDIATE")

        # Khóa lại chính xác trạng thái nền trong transaction.
        current = one_dict(
            conn,
            """
            SELECT a.*,b.school_year_id,b.commune_id AS batch_commune_id,
                   b.is_locked AS batch_is_locked,
                   COALESCE(es.is_commune_locked,0) AS commune_locked,
                   COALESCE(es.is_province_locked,0) AS province_locked
            FROM survey_school_assignments a
            JOIN survey_batches b ON b.id=a.survey_batch_id
            LEFT JOIN survey_commune_execution_states es
                   ON es.survey_batch_id=b.id
            WHERE a.id=?
            """,
            (c["id"],)
        )

        if not current:
            fail("Assignment biến mất trước transaction")
        if str(current["status"]) != "DA_GUI_XA":
            fail("Assignment status đã thay đổi")
        if int(current["is_locked"] or 0) != 0:
            fail("Assignment đã được khóa bởi tiến trình khác")
        if int(current["batch_is_locked"] or 0) != 0:
            fail("Batch vừa bị khóa bởi tiến trình khác")
        if int(current["commune_locked"] or 0) != 0 or int(current["province_locked"] or 0) != 0:
            fail("Xã/Sở vừa bị khóa bởi tiến trình khác")

        # Gọi lại helper source ngay trong thời điểm chuẩn bị ghi.
        # Helper dùng session SQLAlchemy riêng nhưng DB chưa có write khác;
        # vì transaction này chưa update nên kết quả phải giữ nguyên.
        counts2 = call_counts_helper(
            helper,
            int(current["survey_batch_id"]),
            int(current["school_id"]),
        )
        log("SOURCE_HELPER_COUNTS_RECHECK =", json.dumps(counts2, ensure_ascii=False, default=str))

        form_total2 = int(counts2.get("form_total") or 0)
        completed_total2 = int(counts2.get("completed_total") or 0)
        if form_total2 != form_total or completed_total2 != completed_total:
            fail("Tiến độ thay đổi giữa preview và transaction")
        if form_total2 <= 0 or completed_total2 != form_total2:
            fail("Không còn đạt điều kiện 100%")

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")

        cur = conn.execute(
            """
            UPDATE survey_school_assignments
            SET is_locked=1,
                locked_at=?,
                locked_by_user_id=?,
                lock_reason=?,
                status='DA_HOAN_THANH',
                reviewed_at=?,
                updated_at=?
            WHERE id=?
              AND status='DA_GUI_XA'
              AND COALESCE(is_locked,0)=0
            """,
            (
                now,
                actor["id"],
                LOCK_REASON,
                now,
                now,
                c["id"],
            )
        )
        if cur.rowcount != 1:
            fail("UPDATE assignment không đúng 1 dòng")

        insert_workflow_log(
            conn,
            batch_id=int(current["survey_batch_id"]),
            school_id=int(current["school_id"]),
            actor=actor,
            form_total=form_total2,
            completed_total=completed_total2,
        )

        post = one_dict(
            conn,
            "SELECT * FROM survey_school_assignments WHERE id=?",
            (c["id"],)
        )
        if (
            int(post["is_locked"] or 0) != 1
            or str(post["status"]) != "DA_HOAN_THANH"
            or int(post["locked_by_user_id"]) != actor["id"]
        ):
            fail("Post assignment trong transaction không đạt")

        post_log_count = conn.execute(
            "SELECT COUNT(*) FROM survey_execution_workflow_logs"
        ).fetchone()[0]
        if post_log_count != pre_log_count + 1:
            fail("Không tạo đúng 1 workflow log")

        latest = one_dict(
            conn,
            """
            SELECT * FROM survey_execution_workflow_logs
            ORDER BY id DESC LIMIT 1
            """
        )
        log("NEW_WORKFLOW_LOG =", json.dumps(latest, ensure_ascii=False, default=str))
        if (
            int(latest.get("survey_batch_id") or 0) != TARGET_BATCH_ID
            or int(latest.get("school_id") or 0) != int(current["school_id"])
            or str(latest.get("action") or "") != "KHOA_TRUONG"
        ):
            fail("Workflow log mới không đúng")

        fk = conn.execute("PRAGMA foreign_key_check").fetchall()
        if fk:
            fail(f"FK lỗi trước COMMIT: {fk[:20]}")

        conn.commit()
        log("TRANSACTION_COMMIT = PASS")
    except Exception:
        conn.rollback()
        log("TRANSACTION_ROLLBACK = PASS")
        raise
    finally:
        conn.close()

    # Post verify read-only.
    ro = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True, timeout=30)
    try:
        integ = ro.execute("PRAGMA integrity_check").fetchone()[0]
        fk = ro.execute("PRAGMA foreign_key_check").fetchall()
        assignment_after = one_dict(
            ro,
            "SELECT * FROM survey_school_assignments WHERE id=?",
            (c["id"],)
        )
        batch_after = full_batch_safety(ro, TARGET_BATCH_ID)

        log("\n" + "="*160)
        log("POST VERIFY BATCH 07")
        log("="*160)
        log("INTEGRITY_AFTER =", integ)
        log("FK_AFTER =", len(fk))
        log("ASSIGNMENT_AFTER =", json.dumps(assignment_after, ensure_ascii=False, default=str))
        log("BATCH_STATE_AFTER =", json.dumps(batch_after, ensure_ascii=False, default=str))
        log("DB_SHA_AFTER =", sha256_file(DB))

        if integ != "ok" or fk:
            fail("Post verify DB không đạt")

        log("SCHOOL_LOCK_COMMITTED = YES")
        log("COMMUNE_LOCK_WRITES = 0")
        log("PROVINCE_LOCK_WRITES = 0")
        log("BATCH_07_SUCCESS = YES")
        log(
            "NEXT_STAGE = Batch 08 chỉ xem xét khóa xã 114 nếu source code xác nhận "
            "mọi trường thực sự có phiếu đều đã khóa/xác nhận hoàn thành; "
            "129 xã chưa có dữ liệu tiếp tục giữ CHUAN_BI."
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
            log("BATCH_07_SUCCESS = NO")
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
