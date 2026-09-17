# -*- coding: utf-8 -*-
from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
import sys
from collections import defaultdict
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

OUT = EXPORT_DIR / "BATCH_NGHIEP_VU_CON_LAI_TOAN_TINH_09.txt"
DEFERRED_CSV = EXPORT_DIR / "BATCH_09_TRUONG_DEFERRED_CAN_XU_LY_RIENG.csv"

# Nền sau Batch 07B / Batch 08 chỉ đọc.
EXPECTED_DB_SHA = "8899ba224b3d88e7e66f92d67b1dd83adf76667022986c06ebc3b109863a22a2"

BASE_YEAR_ID = 1
CURRENT_YEAR_ID = 2
FUTURE_YEAR_ID = 8

MANUAL_SPLIT_SOURCE_IDS = {1510, 1522, 1658}

TARGET_TABLES = (
    "school_mn01_gv_inputs",
    "school_network_year_data",
    "school_structured_report_inputs",
)

# Không tự clone bảng nào có dấu vết workflow/khóa/trạng thái duyệt.
DANGEROUS_COLUMNS = {
    "is_locked", "locked_at", "locked_by_user_id", "lock_reason",
    "submitted_at", "submitted_by_user_id", "reviewed_at", "reviewed_by_user_id",
    "approved_at", "approved_by_user_id", "rejected_at", "rejected_by_user_id",
    "status_before_lock",
}

# FK ngoài school/year/user-audit có thể khiến dữ liệu năm cũ trỏ sang object năm cũ.
SAFE_FK_COLUMNS = {
    "school_id", "school_year_id",
    "created_by_user_id", "updated_by_user_id",
}

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


def fk_info(conn, table):
    return conn.execute(f"PRAGMA foreign_key_list({qi(table)})").fetchall()


def unique_indexes(conn, table):
    out = []
    for row in conn.execute(f"PRAGMA index_list({qi(table)})").fetchall():
        if int(row[2] or 0) != 1:
            continue
        idx_name = row[1]
        idx_cols = [
            x[2] for x in conn.execute(
                f"PRAGMA index_info({qi(idx_name)})"
            ).fetchall()
        ]
        out.append((idx_name, idx_cols))
    return out


def school(conn, sid):
    return conn.execute(
        "SELECT id,commune_id,code,name,is_active FROM schools WHERE id=?",
        (sid,)
    ).fetchone()


def active_school_ids(conn):
    return [int(r[0]) for r in conn.execute(
        "SELECT id FROM schools WHERE is_active=1 ORDER BY id"
    ).fetchall()]


def official_target_ids(conn):
    return {
        int(r[0]) for r in conn.execute(
            """
            SELECT DISTINCT target_school_id
            FROM school_merger_official_executions
            WHERE school_year_id=?
              AND target_school_id IS NOT NULL
            """,
            (CURRENT_YEAR_ID,)
        ).fetchall()
    }


def renamed_current_ids(conn):
    if not table_exists(conn, "school_name_histories"):
        return set()
    return {
        int(r[0]) for r in conn.execute(
            """
            SELECT DISTINCT school_id
            FROM school_name_histories
            WHERE effective_school_year_id=?
            """,
            (CURRENT_YEAR_ID,)
        ).fetchall()
    }


def protected_reason_map(conn):
    reasons = defaultdict(list)

    for sid in official_target_ids(conn):
        reasons[sid].append("OFFICIAL_MERGER_TARGET")

    for sid in renamed_current_ids(conn):
        reasons[sid].append("RENAMED_CURRENT_YEAR")

    for sid in MANUAL_SPLIT_SOURCE_IDS:
        reasons[sid].append("MANUAL_SPLIT_SOURCE")

    return reasons


def count_school_year(conn, table, sid, year_id):
    return int(conn.execute(
        f"SELECT COUNT(*) FROM {qi(table)} "
        "WHERE school_id=? AND school_year_id=?",
        (sid, year_id)
    ).fetchone()[0])


def read_rows(conn, table, sid, year_id):
    cur = conn.execute(
        f"SELECT * FROM {qi(table)} "
        "WHERE school_id=? AND school_year_id=? "
        + ("ORDER BY id" if "id" in cols(conn, table) else ""),
        (sid, year_id)
    )
    names = [d[0] for d in cur.description]
    return [dict(zip(names, r)) for r in cur.fetchall()]


def schema_gate(conn, table):
    if not table_exists(conn, table):
        return False, ["TABLE_NOT_FOUND"]

    c = cols(conn, table)
    reasons = []

    for req in ("id", "school_id", "school_year_id"):
        if req not in c:
            reasons.append("MISSING_" + req.upper())

    dangerous = sorted(set(c) & DANGEROUS_COLUMNS)
    if dangerous:
        reasons.append("DANGEROUS_COLUMNS=" + ",".join(dangerous))

    unsafe_fk = []
    for fk in fk_info(conn, table):
        from_col = fk[3]
        if from_col not in SAFE_FK_COLUMNS:
            unsafe_fk.append((from_col, fk[2], fk[4]))
    if unsafe_fk:
        reasons.append("UNSAFE_FK=" + json.dumps(unsafe_fk, ensure_ascii=False))

    unsafe_unique = []
    for idx_name, idx_cols in unique_indexes(conn, table):
        meaningful = [x for x in idx_cols if x != "id"]
        if meaningful and "school_year_id" not in meaningful:
            unsafe_unique.append((idx_name, meaningful))
    if unsafe_unique:
        reasons.append("UNSAFE_UNIQUE=" + json.dumps(unsafe_unique, ensure_ascii=False))

    return len(reasons) == 0, reasons


def old_rows_hash(conn, table):
    if "id" not in cols(conn, table):
        return None
    max_id = int(conn.execute(
        f"SELECT COALESCE(MAX(id),0) FROM {qi(table)}"
    ).fetchone()[0])
    cur = conn.execute(
        f"SELECT * FROM {qi(table)} WHERE id<=? ORDER BY id",
        (max_id,)
    )
    names = [d[0] for d in cur.description]
    rows = []
    for r in cur.fetchall():
        rows.append({
            names[i]: (
                {"__blob_sha256__": hashlib.sha256(bytes(v)).hexdigest()}
                if isinstance((v := r[i]), (bytes, bytearray))
                else v
            )
            for i in range(len(names))
        })
    h = hashlib.sha256(
        json.dumps(rows, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    return max_id, h


def verify_old_rows_hash(conn, table, baseline):
    if baseline is None:
        return True
    max_id, old_hash = baseline
    cur = conn.execute(
        f"SELECT * FROM {qi(table)} WHERE id<=? ORDER BY id",
        (max_id,)
    )
    names = [d[0] for d in cur.description]
    rows = []
    for r in cur.fetchall():
        rows.append({
            names[i]: (
                {"__blob_sha256__": hashlib.sha256(bytes(v)).hexdigest()}
                if isinstance((v := r[i]), (bytes, bytearray))
                else v
            )
            for i in range(len(names))
        })
    new_hash = hashlib.sha256(
        json.dumps(rows, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    return old_hash == new_hash


def clone_rows(conn, table, rows):
    info = table_info(conn, table)
    insert_cols = [r[1] for r in info if r[1] != "id"]

    sql = (
        f"INSERT INTO {qi(table)} "
        f"({', '.join(qi(c) for c in insert_cols)}) "
        f"VALUES ({', '.join('?' for _ in insert_cols)})"
    )

    created = 0
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")

    for row in rows:
        d = dict(row)
        d["school_year_id"] = CURRENT_YEAR_ID

        # Audit fields: không mạo danh người nhập cũ nếu nullable.
        col_meta = {r[1]: r for r in info}
        for c in ("created_by_user_id", "updated_by_user_id"):
            if c in d:
                notnull = int(col_meta[c][3] or 0)
                if not notnull:
                    d[c] = None

        if "created_at" in d:
            d["created_at"] = now
        if "updated_at" in d:
            d["updated_at"] = now

        conn.execute(sql, [d.get(c) for c in insert_cols])
        created += 1

    return created


def make_backup():
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = BACKUP_DIR / f"backup_truoc_BATCH_NGHIEP_VU_09_{ts}.db"

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


def prepare_table_plan(conn, table, protected):
    gate_ok, gate_reasons = schema_gate(conn, table)
    plan = {
        "table": table,
        "gate_ok": gate_ok,
        "gate_reasons": gate_reasons,
        "safe_schools": [],
        "protected_schools": [],
        "already_y2": [],
        "no_y1": [],
    }

    if not gate_ok:
        return plan

    for sid in active_school_ids(conn):
        y1 = count_school_year(conn, table, sid, BASE_YEAR_ID)
        y2 = count_school_year(conn, table, sid, CURRENT_YEAR_ID)

        if y2 > 0:
            plan["already_y2"].append((sid, y1, y2))
            continue
        if y1 == 0:
            plan["no_y1"].append(sid)
            continue

        if sid in protected:
            plan["protected_schools"].append({
                "school_id": sid,
                "school": school(conn, sid),
                "reasons": protected[sid],
                "y1_rows": y1,
            })
            continue

        plan["safe_schools"].append({
            "school_id": sid,
            "school": school(conn, sid),
            "y1_rows": y1,
        })

    return plan


def execute_table(conn, plan):
    table = plan["table"]
    if not plan["gate_ok"]:
        log("TABLE", table, "SKIP_SCHEMA_GATE =", plan["gate_reasons"])
        return {"status": "SKIP_SCHEMA_GATE", "inserted": 0}

    safe = plan["safe_schools"]
    if not safe:
        log("TABLE", table, "SKIP_NO_SAFE_SCHOOLS")
        return {"status": "SKIP_NO_SAFE_SCHOOLS", "inserted": 0}

    expected = sum(int(x["y1_rows"]) for x in safe)
    baseline = old_rows_hash(conn, table)

    log("\n" + "-" * 150)
    log("TABLE_WRITE_START =", table)
    log("SAFE_SCHOOL_COUNT =", len(safe))
    log("EXPECTED_INSERT_ROWS =", expected)
    log("PROTECTED_SCHOOL_COUNT =", len(plan["protected_schools"]))

    conn.execute("BEGIN IMMEDIATE")
    try:
        created = 0

        for item in safe:
            sid = int(item["school_id"])

            # Recheck footprint ngay trong transaction.
            y1 = count_school_year(conn, table, sid, BASE_YEAR_ID)
            y2 = count_school_year(conn, table, sid, CURRENT_YEAR_ID)

            if y1 != int(item["y1_rows"]):
                fail(f"{table}: y1 footprint changed school={sid}")
            if y2 != 0:
                fail(f"{table}: y2 appeared before insert school={sid}")

            rows = read_rows(conn, table, sid, BASE_YEAR_ID)
            created += clone_rows(conn, table, rows)

        if created != expected:
            fail(f"{table}: created={created} expected={expected}")

        if not verify_old_rows_hash(conn, table, baseline):
            fail(f"{table}: old rows changed")

        bad = []
        for item in safe:
            sid = int(item["school_id"])
            expected_school = int(item["y1_rows"])
            actual = count_school_year(conn, table, sid, CURRENT_YEAR_ID)
            if actual != expected_school:
                bad.append((sid, expected_school, actual))

        if bad:
            fail(f"{table}: post-count mismatch {bad[:20]}")

        fk = conn.execute("PRAGMA foreign_key_check").fetchall()
        if fk:
            fail(f"{table}: FK errors {fk[:20]}")

        conn.commit()
        log("TABLE_WRITE_COMMIT =", table)
        log("INSERTED_ROWS =", created)
        return {
            "status": "COMMIT",
            "inserted": created,
            "school_count": len(safe),
        }

    except Exception:
        conn.rollback()
        log("TABLE_WRITE_ROLLBACK =", table)
        raise


def main():
    global LOG
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    LOG = OUT.open("w", encoding="utf-8-sig", newline="\n")

    log("=" * 160)
    log("BATCH NGHIỆP VỤ CÒN LẠI TOÀN TỈNH 09")
    log("ROLLOVER DỮ LIỆU NỀN CHO TRƯỜNG ỔN ĐỊNH: MN-01-GV + MẠNG LƯỚI + STRUCTURED REPORT INPUTS")
    log("KHÔNG ĐỤNG MERGER TARGET / ĐỔI TÊN / 3 NGUỒN TÁCH ĐIỂM")
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
        fail("DB SHA khác nền Batch 08")

    ro = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True, timeout=30)
    try:
        integ = ro.execute("PRAGMA integrity_check").fetchone()[0]
        fk = ro.execute("PRAGMA foreign_key_check").fetchall()
        log("INTEGRITY_BEFORE =", integ)
        log("FK_BEFORE =", len(fk))

        if integ != "ok" or fk:
            fail("Database health không đạt")

        protected = protected_reason_map(ro)
        log("PROTECTED_SCHOOL_COUNT =", len(protected))
        log("MANUAL_SPLIT_SOURCE_IDS =", sorted(MANUAL_SPLIT_SOURCE_IDS))

        plans = []
        for table in TARGET_TABLES:
            p = prepare_table_plan(ro, table, protected)
            plans.append(p)

            log("\nTABLE_PLAN =", table)
            log("SCHEMA =", table_info(ro, table) if table_exists(ro, table) else "TABLE_NOT_FOUND")
            log("FOREIGN_KEYS =", fk_info(ro, table) if table_exists(ro, table) else [])
            log("UNIQUE_INDEXES =", unique_indexes(ro, table) if table_exists(ro, table) else [])
            log("GATE_OK =", p["gate_ok"])
            log("GATE_REASONS =", p["gate_reasons"])
            log("SAFE_SCHOOL_COUNT =", len(p["safe_schools"]))
            log("PROTECTED_SCHOOL_COUNT =", len(p["protected_schools"]))
            log("ALREADY_Y2_COUNT =", len(p["already_y2"]))

    finally:
        ro.close()

    # Xuất danh sách deferred trước khi ghi.
    with DEFERRED_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        fields = ["table", "school_id", "school_code", "school_name", "y1_rows", "reasons"]
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()

        for p in plans:
            for x in p["protected_schools"]:
                s = x["school"]
                w.writerow({
                    "table": p["table"],
                    "school_id": x["school_id"],
                    "school_code": s[2] if s else "",
                    "school_name": s[3] if s else "",
                    "y1_rows": x["y1_rows"],
                    "reasons": "|".join(x["reasons"]),
                })

    log("DEFERRED_CSV =", DEFERRED_CSV)

    # Nếu không bảng nào qua schema gate thì không cần backup/ghi.
    if not any(p["gate_ok"] and p["safe_schools"] for p in plans):
        log("NO_WRITE = Không có bảng/trường nào đạt gate.")
        log("BATCH_09_SUCCESS = YES_NO_WRITE")
        if LOG:
            LOG.close()
        return 0

    backup = make_backup()
    log("BACKUP =", backup)
    log("BACKUP_SHA =", sha256_file(backup))

    conn = sqlite3.connect(str(DB), timeout=60)
    conn.execute("PRAGMA foreign_keys=ON")

    results = {}
    try:
        for p in plans:
            results[p["table"]] = execute_table(conn, p)

        integ = conn.execute("PRAGMA integrity_check").fetchone()[0]
        fk = conn.execute("PRAGMA foreign_key_check").fetchall()

        log("\n" + "=" * 160)
        log("POST VERIFY BATCH 09")
        log("=" * 160)
        log("INTEGRITY_AFTER =", integ)
        log("FK_AFTER =", len(fk))
        log("RESULTS =", json.dumps(results, ensure_ascii=False, default=str))
        log("DB_SHA_AFTER =", sha256_file(DB))

        if integ != "ok" or fk:
            fail("Post verify Batch 09 không đạt")

        # Rà lại các khoảng trống còn lại ở 3 bảng.
        for table in TARGET_TABLES:
            if not table_exists(conn, table):
                continue
            missing = []
            for sid in active_school_ids(conn):
                y1 = count_school_year(conn, table, sid, BASE_YEAR_ID)
                y2 = count_school_year(conn, table, sid, CURRENT_YEAR_ID)
                if y1 > 0 and y2 == 0:
                    missing.append((sid, protected.get(sid, []), school(conn, sid)))
            log("REMAINING_MISSING_Y2", table, "COUNT =", len(missing))
            for row in missing[:200]:
                log(" REMAINING =", row)

        log("STAFF_MANUAL_SPLIT_POLICY = 1510/1522/1658 vẫn không tự rollover.")
        log("FINANCE_FACILITY_HISTORY_POLICY = baseline trống thì không tự tạo dữ liệu giả.")
        log("BATCH_09_SUCCESS = YES")
        log(
            "NEXT_STAGE = Batch 10 xử lý riêng các trường merger target/đổi tên còn deferred "
            "bằng quy tắc tổng hợp theo official merger; đồng thời rà đối chiếu học sinh, "
            "khuyết tật, CSVC-TBDH, tài chính và báo cáo để đóng các nhóm không có baseline."
        )
        log("=" * 160)
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
            log("\n" + "=" * 160)
            log("BATCH_09_SUCCESS = NO")
            log("ERROR =", repr(exc))
            if DB.exists():
                log("DB_SHA_CURRENT =", sha256_file(DB))
            log("DỪNG AN TOÀN.")
            log("=" * 160)
        finally:
            if LOG and not LOG.closed:
                LOG.close()
        code = 1

    sys.exit(code)
