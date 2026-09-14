# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from collections import Counter, defaultdict
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
OUT = EXPORT_DIR / "BATCH_DU_LIEU_HAU_SAP_NHAP_TOAN_TINH_02.txt"

EXPECTED_DB_SHA = "164620f214a0820a07b93d35f877b917c4cc66ca54e0326e7265a7a3b3b8ee01"

BASE_YEAR_ID = 1
CURRENT_YEAR_ID = 2
FUTURE_YEAR_ID = 8

# 5 nguồn đặc thù chưa được phép tự động rollover cùng trường.
# Giữ nguyên để xử lý riêng bằng dữ liệu điểm/lớp thực tế, tránh tạo trạng thái hiện hành sai.
BLOCKED_MANUAL_SOURCE_IDS = {1522, 1583, 1580, 1510, 1658}

EXCLUDED_STATUS_CODES = {"NGHI_HUU", "CHUYEN_DI", "THOI_VIEC", "DA_NGHI"}
EXCLUDED_STATUS_LABELS = {"Đã nghỉ hưu", "Đã chuyển đi", "Nghỉ hưu", "Chuyển đi"}

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

def table_exists(conn, table):
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,)
    ).fetchone() is not None

def table_info(conn, table):
    return conn.execute(f"PRAGMA table_info({qi(table)})").fetchall()

def cols(conn, table):
    return [r[1] for r in table_info(conn, table)]

def table_count(conn, table):
    return int(conn.execute(f"SELECT COUNT(*) FROM {qi(table)}").fetchone()[0])

def rows_hash(cur):
    names = [d[0] for d in cur.description]
    rows = []
    for r in cur.fetchall():
        d = {}
        for i, n in enumerate(names):
            v = r[i]
            if isinstance(v, (bytes, bytearray)):
                v = {"__blob_sha256__": hashlib.sha256(bytes(v)).hexdigest()}
            d[n] = v
        rows.append(d)
    return hashlib.sha256(
        json.dumps(rows, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()

def old_rows_baseline(conn, table):
    c = cols(conn, table)
    if "id" not in c:
        return None
    max_id = int(conn.execute(f"SELECT COALESCE(MAX(id),0) FROM {qi(table)}").fetchone()[0])
    old_hash = rows_hash(conn.execute(f"SELECT * FROM {qi(table)} WHERE id<=? ORDER BY id", (max_id,)))
    return max_id, old_hash

def old_rows_unchanged(conn, table, baseline):
    if baseline is None:
        return True
    max_id, old_hash = baseline
    now_hash = rows_hash(conn.execute(f"SELECT * FROM {qi(table)} WHERE id<=? ORDER BY id", (max_id,)))
    return now_hash == old_hash

def make_backup():
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = BACKUP_DIR / f"backup_truoc_BATCH_DU_LIEU_02_{ts}.db"

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
        fail(f"Backup không đạt: integrity={integ}, fk={len(fk)}")
    return path

def school(conn, sid):
    return conn.execute(
        "SELECT id,commune_id,code,name,is_active FROM schools WHERE id=?",
        (sid,)
    ).fetchone()

def active_school_ids(conn):
    return [
        int(r[0]) for r in conn.execute(
            "SELECT id FROM schools WHERE is_active=1 ORDER BY id"
        ).fetchall()
    ]

def safe_count(conn, table, sid, year_id):
    return int(conn.execute(
        f"SELECT COUNT(*) FROM {qi(table)} WHERE school_id=? AND school_year_id=?",
        (sid, year_id)
    ).fetchone()[0])

def read_rows(conn, table, sid, year_id):
    cur = conn.execute(
        f"SELECT * FROM {qi(table)} WHERE school_id=? AND school_year_id=? ORDER BY id",
        (sid, year_id)
    )
    names = [d[0] for d in cur.description]
    return [dict(zip(names, r)) for r in cur.fetchall()]

def clone_rows_generic(conn, table, source_rows, mutate):
    info = table_info(conn, table)
    insert_cols = [r[1] for r in info if r[1] != "id"]
    sql = (
        f"INSERT INTO {qi(table)} ({', '.join(qi(c) for c in insert_cols)}) "
        f"VALUES ({', '.join('?' for _ in insert_cols)})"
    )
    created = 0
    for row in source_rows:
        d = dict(row)
        mutate(d)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
        if "created_at" in d:
            d["created_at"] = now
        if "updated_at" in d:
            d["updated_at"] = now
        conn.execute(sql, [d.get(c) for c in insert_cols])
        created += 1
    return created

def unique_indexes(conn, table):
    out = []
    for r in conn.execute(f"PRAGMA index_list({qi(table)})").fetchall():
        # seq, name, unique, origin, partial
        if int(r[2] or 0) != 1:
            continue
        name = r[1]
        icols = [x[2] for x in conn.execute(f"PRAGMA index_info({qi(name)})").fetchall()]
        out.append((name, icols))
    return out

def year_scoped_unique_ok(conn, table):
    bad = []
    for name, icols in unique_indexes(conn, table):
        meaningful = [c for c in icols if c != "id"]
        if not meaningful:
            continue
        if "school_year_id" not in meaningful:
            bad.append((name, meaningful))
    return bad

def active_school_login_audit(conn):
    """
    role_id=3 hiện chứa cả tài khoản cbql.* và tài khoản trường.
    Chỉ coi username bắt đầu bằng 'truong_' là tài khoản trường chính.
    Không vô hiệu hóa cbql.*.
    """
    anomalies = []
    info = []
    for sid in active_school_ids(conn):
        rows = conn.execute(
            "SELECT id,username,is_active FROM users WHERE school_id=? AND role_id=3 ORDER BY id",
            (sid,)
        ).fetchall()
        active_school_accounts = [
            r for r in rows
            if int(r[2] or 0) == 1 and str(r[1] or "").lower().startswith("truong_")
        ]
        active_cbql = [
            r for r in rows
            if int(r[2] or 0) == 1 and str(r[1] or "").lower().startswith("cbql.")
        ]
        if len(active_school_accounts) != 1:
            anomalies.append((sid, school(conn, sid), rows))
        if active_cbql:
            info.append((sid, len(active_cbql)))
    return anomalies, info

def staff_candidates(conn):
    active_ids = active_school_ids(conn)
    candidates = []
    blocked = []
    for sid in active_ids:
        y1 = safe_count(conn, "staff_year_records", sid, BASE_YEAR_ID)
        y2 = safe_count(conn, "staff_year_records", sid, CURRENT_YEAR_ID)
        if y1 > 0 and y2 == 0:
            if sid in BLOCKED_MANUAL_SOURCE_IDS:
                blocked.append((sid, y1, school(conn, sid)))
            else:
                candidates.append((sid, y1, school(conn, sid)))
    return candidates, blocked

def staff_row_eligible(row):
    if "is_active" in row and int(row.get("is_active") or 0) != 1:
        return False, "is_active!=1"
    status = str(row.get("status_code") or "").strip().upper()
    label = str(row.get("source_status_label") or "").strip()
    if status in EXCLUDED_STATUS_CODES:
        return False, "status_code=" + status
    if label in EXCLUDED_STATUS_LABELS:
        return False, "source_status_label=" + label
    return True, ""

def prepare_staff_rollover(conn):
    candidates, blocked = staff_candidates(conn)

    safe_schools = []
    conflict_schools = []
    excluded_counter = Counter()
    safe_rows_by_school = {}

    for sid, y1_count, s in candidates:
        rows = read_rows(conn, "staff_year_records", sid, BASE_YEAR_ID)
        eligible = []
        excluded = []

        for r in rows:
            ok, why = staff_row_eligible(r)
            if ok:
                eligible.append(r)
            else:
                excluded.append((int(r.get("staff_member_id")), why))
                excluded_counter[why] += 1

        member_ids = [int(r["staff_member_id"]) for r in eligible]
        if len(member_ids) != len(set(member_ids)):
            conflict_schools.append((sid, "DUPLICATE_MEMBER_IN_Y1", s))
            continue

        existing_y2 = []
        if member_ids:
            q = ",".join("?" for _ in member_ids)
            existing_y2 = conn.execute(
                f"SELECT staff_member_id,school_id FROM staff_year_records "
                f"WHERE school_year_id=? AND staff_member_id IN ({q}) "
                f"ORDER BY staff_member_id,school_id",
                [CURRENT_YEAR_ID] + member_ids
            ).fetchall()

        if existing_y2:
            conflict_schools.append((sid, "MEMBER_ALREADY_HAS_Y2", existing_y2[:30], s))
            continue

        safe_schools.append((sid, len(rows), len(eligible), len(excluded), s))
        safe_rows_by_school[sid] = eligible

    return {
        "candidates": candidates,
        "blocked": blocked,
        "safe_schools": safe_schools,
        "conflict_schools": conflict_schools,
        "excluded_counter": excluded_counter,
        "safe_rows_by_school": safe_rows_by_school,
    }

def duplicate_staff_y2(conn):
    return conn.execute(
        """
        SELECT staff_member_id,COUNT(*),GROUP_CONCAT(school_id)
        FROM staff_year_records
        WHERE school_year_id=?
        GROUP BY staff_member_id
        HAVING COUNT(*)>1
        ORDER BY staff_member_id
        """,
        (CURRENT_YEAR_ID,)
    ).fetchall()

def transaction_staff(conn):
    plan = prepare_staff_rollover(conn)

    log("\n" + "="*160)
    log("TRANSACTION A - STAFF ROLLOVER AN TOÀN")
    log("="*160)
    log("STAFF_CANDIDATE_SCHOOLS =", len(plan["candidates"]))
    log("BLOCKED_MANUAL_SOURCE_SCHOOLS =", len(plan["blocked"]), plan["blocked"])
    log("SAFE_STAFF_SCHOOLS =", len(plan["safe_schools"]))
    log("CONFLICT_STAFF_SCHOOLS =", len(plan["conflict_schools"]))
    for x in plan["conflict_schools"][:100]:
        log(" STAFF_CONFLICT =", x)
    log("EXCLUDED_STATUS_COUNTER =", dict(plan["excluded_counter"]))

    expected_insert = sum(x[2] for x in plan["safe_schools"])
    log("EXPECTED_STAFF_INSERT_ROWS =", expected_insert)

    if not plan["safe_schools"]:
        log("STAFF_TRANSACTION = SKIP_NO_SAFE_SCHOOLS")
        return {"status": "SKIP", "inserted": 0, "plan": plan}

    old_baseline = old_rows_baseline(conn, "staff_year_records")
    other_counts_before = {
        t: table_count(conn, t)
        for t in ("schools", "users", "classes", "student_enrollments")
        if table_exists(conn, t)
    }

    conn.execute("BEGIN IMMEDIATE")
    try:
        created = 0
        for sid, _, eligible_count, _, _ in plan["safe_schools"]:
            rows = plan["safe_rows_by_school"][sid]

            def mutate(d, sid=sid):
                d["school_id"] = sid
                d["school_year_id"] = CURRENT_YEAR_ID

            created += clone_rows_generic(conn, "staff_year_records", rows, mutate)

        if created != expected_insert:
            fail(f"Staff created {created} != expected {expected_insert}")

        # Không được sửa record cũ.
        if not old_rows_unchanged(conn, "staff_year_records", old_baseline):
            fail("staff_year_records cũ bị thay đổi")

        # Các bảng khác không được đổi số dòng.
        other_counts_after = {
            t: table_count(conn, t) for t in other_counts_before
        }
        if other_counts_after != other_counts_before:
            fail(f"Bảng ngoài staff bị đổi count: {other_counts_before} -> {other_counts_after}")

        # Mỗi school safe phải có đúng số eligible ở y2.
        bad = []
        for sid, _, eligible_count, _, _ in plan["safe_schools"]:
            y2 = safe_count(conn, "staff_year_records", sid, CURRENT_YEAR_ID)
            if y2 != eligible_count:
                bad.append((sid, eligible_count, y2))
        if bad:
            fail(f"Staff post-count sai: {bad[:20]}")

        dups = duplicate_staff_y2(conn)
        if dups:
            fail(f"Duplicate staff y2 phát sinh: {dups[:20]}")

        fk = conn.execute("PRAGMA foreign_key_check").fetchall()
        if fk:
            fail(f"FK lỗi trong staff transaction: {fk[:20]}")

        conn.commit()
        log("STAFF_TRANSACTION = COMMIT")
        log("STAFF_INSERTED =", created)
        return {"status": "COMMIT", "inserted": created, "plan": plan}

    except Exception:
        conn.rollback()
        log("STAFF_TRANSACTION = ROLLBACK")
        raise

def class_key(row):
    exclude = {"id", "school_year_id", "created_at", "updated_at"}
    return json.dumps(
        {k: v for k, v in row.items() if k not in exclude},
        ensure_ascii=False, sort_keys=True, default=str
    )

def transaction_classes(conn):
    log("\n" + "="*160)
    log("TRANSACTION B - CLASSES ROLLOVER AN TOÀN")
    log("="*160)

    if not table_exists(conn, "classes"):
        log("CLASSES_TRANSACTION = SKIP_TABLE_NOT_FOUND")
        return {"status": "SKIP"}

    log("CLASSES_SCHEMA =", table_info(conn, "classes"))
    log("CLASSES_UNIQUE_INDEXES =", unique_indexes(conn, "classes"))
    bad_unique = year_scoped_unique_ok(conn, "classes")
    if bad_unique:
        log("CLASSES_TRANSACTION = SKIP_UNSAFE_UNIQUE_INDEX")
        log("UNSAFE_UNIQUE_INDEXES =", bad_unique)
        return {"status": "SKIP_UNSAFE_UNIQUE", "bad_unique": bad_unique}

    candidates = []
    for sid in active_school_ids(conn):
        if sid in BLOCKED_MANUAL_SOURCE_IDS:
            continue
        y1 = safe_count(conn, "classes", sid, BASE_YEAR_ID)
        y2 = safe_count(conn, "classes", sid, CURRENT_YEAR_ID)
        if y1 > 0 and y2 == 0:
            candidates.append((sid, y1, school(conn, sid)))

    log("CLASS_CANDIDATE_SCHOOLS =", len(candidates))
    for row in candidates:
        log(" CLASS_CANDIDATE =", row)

    if not candidates:
        log("CLASSES_TRANSACTION = SKIP_NO_CANDIDATES")
        return {"status": "SKIP"}

    old_baseline = old_rows_baseline(conn, "classes")
    expected = sum(x[1] for x in candidates)

    conn.execute("BEGIN IMMEDIATE")
    try:
        created = 0
        for sid, y1, _ in candidates:
            rows = read_rows(conn, "classes", sid, BASE_YEAR_ID)
            def mutate(d, sid=sid):
                d["school_id"] = sid
                d["school_year_id"] = CURRENT_YEAR_ID
            created += clone_rows_generic(conn, "classes", rows, mutate)

        if created != expected:
            fail(f"Class created {created} != expected {expected}")
        if not old_rows_unchanged(conn, "classes", old_baseline):
            fail("classes cũ bị thay đổi")

        bad = []
        for sid, y1, _ in candidates:
            y2 = safe_count(conn, "classes", sid, CURRENT_YEAR_ID)
            if y2 != y1:
                bad.append((sid, y1, y2))
        if bad:
            fail(f"Class post-count sai: {bad}")

        fk = conn.execute("PRAGMA foreign_key_check").fetchall()
        if fk:
            fail(f"FK lỗi classes: {fk[:20]}")

        conn.commit()
        log("CLASSES_TRANSACTION = COMMIT")
        log("CLASSES_INSERTED =", created)
        return {"status": "COMMIT", "inserted": created, "candidates": candidates}

    except Exception as exc:
        conn.rollback()
        log("CLASSES_TRANSACTION = ROLLBACK")
        log("CLASSES_ERROR =", repr(exc))
        return {"status": "ROLLBACK", "error": repr(exc), "candidates": candidates}

def build_class_map(conn, sid):
    y1 = read_rows(conn, "classes", sid, BASE_YEAR_ID)
    y2 = read_rows(conn, "classes", sid, CURRENT_YEAR_ID)

    by1 = defaultdict(list)
    by2 = defaultdict(list)
    for r in y1:
        by1[class_key(r)].append(r)
    for r in y2:
        by2[class_key(r)].append(r)

    mapping = {}
    ambiguous = []
    for key, old_rows in by1.items():
        new_rows = by2.get(key, [])
        if len(old_rows) != 1 or len(new_rows) != 1:
            ambiguous.append((key, len(old_rows), len(new_rows)))
            continue
        mapping[int(old_rows[0]["id"])] = int(new_rows[0]["id"])

    if len(mapping) != len(y1):
        return None, ambiguous
    return mapping, []

def transaction_enrollments(conn):
    log("\n" + "="*160)
    log("TRANSACTION C - STUDENT ENROLLMENTS ROLLOVER AN TOÀN")
    log("="*160)

    if not table_exists(conn, "student_enrollments"):
        log("ENROLLMENT_TRANSACTION = SKIP_TABLE_NOT_FOUND")
        return {"status": "SKIP"}

    log("STUDENT_ENROLLMENTS_SCHEMA =", table_info(conn, "student_enrollments"))
    log("STUDENT_ENROLLMENTS_UNIQUE_INDEXES =", unique_indexes(conn, "student_enrollments"))
    bad_unique = year_scoped_unique_ok(conn, "student_enrollments")
    if bad_unique:
        log("ENROLLMENT_TRANSACTION = SKIP_UNSAFE_UNIQUE_INDEX")
        log("UNSAFE_UNIQUE_INDEXES =", bad_unique)
        return {"status": "SKIP_UNSAFE_UNIQUE", "bad_unique": bad_unique}

    candidates = []
    for sid in active_school_ids(conn):
        if sid in BLOCKED_MANUAL_SOURCE_IDS:
            continue
        y1 = safe_count(conn, "student_enrollments", sid, BASE_YEAR_ID)
        y2 = safe_count(conn, "student_enrollments", sid, CURRENT_YEAR_ID)
        if y1 > 0 and y2 == 0:
            candidates.append((sid, y1, school(conn, sid)))

    log("ENROLLMENT_CANDIDATE_SCHOOLS =", len(candidates))
    for row in candidates:
        log(" ENROLLMENT_CANDIDATE =", row)

    if not candidates:
        log("ENROLLMENT_TRANSACTION = SKIP_NO_CANDIDATES")
        return {"status": "SKIP"}

    enrollment_cols = cols(conn, "student_enrollments")
    has_class_id = "class_id" in enrollment_cols

    class_maps = {}
    if has_class_id:
        if not table_exists(conn, "classes"):
            log("ENROLLMENT_TRANSACTION = SKIP_NO_CLASSES_TABLE")
            return {"status": "SKIP_NO_CLASSES"}

        for sid, _, _ in candidates:
            mapping, ambiguous = build_class_map(conn, sid)
            if mapping is None:
                log("ENROLLMENT_TRANSACTION = SKIP_CLASS_MAP_AMBIGUOUS")
                log(" SCHOOL =", sid, "AMBIGUOUS =", ambiguous[:30])
                return {"status": "SKIP_CLASS_MAP", "school_id": sid, "ambiguous": ambiguous}
            class_maps[sid] = mapping
            log(" CLASS_MAP_SIZE", sid, "=", len(mapping))

    # Nếu có cột nhận diện HS, không cho nhân đôi người đã có y2 ở nơi khác.
    identity_col = next(
        (c for c in ("student_id", "person_id", "student_member_id", "person_member_id")
         if c in enrollment_cols),
        None
    )
    log("ENROLLMENT_IDENTITY_COL =", identity_col)

    conflict_rows = []
    if identity_col:
        ids = []
        for sid, _, _ in candidates:
            for r in read_rows(conn, "student_enrollments", sid, BASE_YEAR_ID):
                v = r.get(identity_col)
                if v is not None:
                    ids.append(v)
        if ids:
            unique_ids = sorted(set(ids), key=lambda x: str(x))
            # Batch theo cụm để tránh quá nhiều bind params.
            for i in range(0, len(unique_ids), 800):
                batch = unique_ids[i:i+800]
                q = ",".join("?" for _ in batch)
                conflict_rows.extend(
                    conn.execute(
                        f"SELECT {qi(identity_col)},school_id FROM student_enrollments "
                        f"WHERE school_year_id=? AND {qi(identity_col)} IN ({q})",
                        [CURRENT_YEAR_ID] + batch
                    ).fetchall()
                )
        if conflict_rows:
            log("ENROLLMENT_TRANSACTION = SKIP_IDENTITY_CONFLICT")
            log("IDENTITY_CONFLICTS =", conflict_rows[:100])
            return {"status": "SKIP_IDENTITY_CONFLICT", "conflicts": conflict_rows}

    old_baseline = old_rows_baseline(conn, "student_enrollments")
    expected = sum(x[1] for x in candidates)

    conn.execute("BEGIN IMMEDIATE")
    try:
        created = 0
        for sid, _, _ in candidates:
            rows = read_rows(conn, "student_enrollments", sid, BASE_YEAR_ID)
            cmap = class_maps.get(sid, {})

            def mutate(d, sid=sid, cmap=cmap):
                d["school_id"] = sid
                d["school_year_id"] = CURRENT_YEAR_ID
                if has_class_id and d.get("class_id") is not None:
                    old_id = int(d["class_id"])
                    if old_id not in cmap:
                        fail(f"Không map được class_id={old_id} school={sid}")
                    d["class_id"] = cmap[old_id]

            created += clone_rows_generic(conn, "student_enrollments", rows, mutate)

        if created != expected:
            fail(f"Enrollment created {created} != expected {expected}")

        if not old_rows_unchanged(conn, "student_enrollments", old_baseline):
            fail("student_enrollments cũ bị thay đổi")

        bad = []
        for sid, y1, _ in candidates:
            y2 = safe_count(conn, "student_enrollments", sid, CURRENT_YEAR_ID)
            if y2 != y1:
                bad.append((sid, y1, y2))
        if bad:
            fail(f"Enrollment post-count sai: {bad}")

        fk = conn.execute("PRAGMA foreign_key_check").fetchall()
        if fk:
            fail(f"FK lỗi enrollments: {fk[:20]}")

        conn.commit()
        log("ENROLLMENT_TRANSACTION = COMMIT")
        log("ENROLLMENTS_INSERTED =", created)
        return {"status": "COMMIT", "inserted": created, "candidates": candidates}

    except Exception as exc:
        conn.rollback()
        log("ENROLLMENT_TRANSACTION = ROLLBACK")
        log("ENROLLMENT_ERROR =", repr(exc))
        return {"status": "ROLLBACK", "error": repr(exc), "candidates": candidates}

def audit_summaries_and_accounts(conn):
    log("\n" + "="*160)
    log("AUDIT SAU BATCH - TÀI KHOẢN + SUMMARY + CÁC BẢNG CÒN LẠI")
    log("="*160)

    account_anom, cbql_info = active_school_login_audit(conn)
    log("ACTIVE_TRUONG_ACCOUNT_ANOMALIES =", len(account_anom))
    for x in account_anom[:100]:
        log(" ACCOUNT_ANOMALY =", x)
    log("ACTIVE_SCHOOLS_WITH_CBQL_ACCOUNTS =", len(cbql_info))
    log("CBQL_ACCOUNTS_POLICY = GIỮ NGUYÊN, KHÔNG COI LÀ TRÙNG TÀI KHOẢN TRƯỜNG")

    if table_exists(conn, "school_staff_year_summaries"):
        log("SCHOOL_STAFF_YEAR_SUMMARIES_SCHEMA =", table_info(conn, "school_staff_year_summaries"))
        log("SCHOOL_STAFF_YEAR_SUMMARIES_UNIQUE_INDEXES =", unique_indexes(conn, "school_staff_year_summaries"))

        missing_summary = []
        for sid in active_school_ids(conn):
            y1 = safe_count(conn, "school_staff_year_summaries", sid, BASE_YEAR_ID)
            y2 = safe_count(conn, "school_staff_year_summaries", sid, CURRENT_YEAR_ID)
            staff_y2 = safe_count(conn, "staff_year_records", sid, CURRENT_YEAR_ID)
            if staff_y2 > 0 and y2 == 0:
                missing_summary.append((sid, y1, staff_y2, school(conn, sid)))
        log("MISSING_STAFF_SUMMARY_FOR_SCHOOLS_WITH_Y2_STAFF =", len(missing_summary))
        for x in missing_summary[:150]:
            log(" MISSING_SUMMARY =", x)

        samples = conn.execute(
            "SELECT * FROM school_staff_year_summaries WHERE school_year_id=? ORDER BY id LIMIT 10",
            (BASE_YEAR_ID,)
        ).fetchall()
        log("STAFF_SUMMARY_Y1_SAMPLE =", samples)

    for table in ("finance_year_entries", "school_facility_year_items", "survey_person_year_records"):
        if not table_exists(conn, table):
            continue
        c = cols(conn, table)
        if "school_year_id" in c:
            y1 = conn.execute(
                f"SELECT COUNT(*) FROM {qi(table)} WHERE school_year_id=?", (BASE_YEAR_ID,)
            ).fetchone()[0]
            y2 = conn.execute(
                f"SELECT COUNT(*) FROM {qi(table)} WHERE school_year_id=?", (CURRENT_YEAR_ID,)
            ).fetchone()[0]
            log("TABLE_REMAINING", table, "Y1=", y1, "Y2=", y2)
        log("SCHEMA", table, "=", table_info(conn, table))

def main():
    global LOG
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    LOG = OUT.open("w", encoding="utf-8-sig", newline="\n")

    log("="*160)
    log("BATCH DỮ LIỆU HẬU SÁP NHẬP TOÀN TỈNH 02")
    log("MỤC TIÊU: ROLLOVER ĐỘI NGŨ + LỚP + HỌC SINH THEO GATE AN TOÀN; KHÔNG ĐỤNG 5 NGUỒN TÁCH ĐIỂM")
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
        fail("DB SHA khác nền đã kiểm toán")

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

    backup = make_backup()
    log("BACKUP =", backup)
    log("BACKUP_SHA =", sha256_file(backup))

    conn = sqlite3.connect(str(DB), timeout=60)
    conn.execute("PRAGMA foreign_keys=ON")

    results = {}
    try:
        results["staff"] = transaction_staff(conn)
        results["classes"] = transaction_classes(conn)
        results["enrollments"] = transaction_enrollments(conn)

        audit_summaries_and_accounts(conn)

        integ = conn.execute("PRAGMA integrity_check").fetchone()[0]
        fk = conn.execute("PRAGMA foreign_key_check").fetchall()
        dups = duplicate_staff_y2(conn)

        log("\n" + "="*160)
        log("POST VERIFY TOÀN BATCH")
        log("="*160)
        log("INTEGRITY_AFTER =", integ)
        log("FK_AFTER =", len(fk))
        log("DUPLICATE_STAFF_Y2_AFTER =", len(dups))
        log("TRANSACTION_RESULTS =", json.dumps({
            k: {
                "status": v.get("status"),
                "inserted": v.get("inserted", 0)
            } for k, v in results.items()
        }, ensure_ascii=False))
        log("DB_SHA_AFTER =", sha256_file(DB))

        if integ != "ok" or fk or dups:
            fail("Post verify toàn batch không đạt")

        log("BATCH_02_SUCCESS = YES")
        log("DATABASE_BACKUP =", backup)
        log("BLOCKED_MANUAL_SOURCE_IDS =", sorted(BLOCKED_MANUAL_SOURCE_IDS))
        log("NEXT_STAGE = Dựa trên schema summary và kết quả account audit để làm Batch 03: summary/CSVC/tài chính/điều tra + 5 ca tách điểm.")
        log("="*160)

        return 0

    finally:
        conn.close()
        if LOG:
            LOG.close()

if __name__ == "__main__":
    try:
        code = main()
    except Exception as exc:
        try:
            log("\n" + "="*160)
            log("BATCH_02_SUCCESS = NO")
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
