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

OUT = EXPORT_DIR / "BATCH_NGHIEP_VU_CON_LAI_TOAN_TINH_11.txt"
NETWORK_DEFERRED_CSV = EXPORT_DIR / "BATCH_11_NETWORK_DEFERRED.csv"
REPORT_AUDIT_JSON = EXPORT_DIR / "BATCH_11_STRUCTURED_REPORT_SOURCE_AUDIT.json"

# Nền ngay sau Batch 10.
EXPECTED_DB_SHA = "5eb8d781548edc4cdb0d600fce070b3ffbb08ec06d32174dbc798b4070fd4bb2"

BASE_YEAR_ID = 1
CURRENT_YEAR_ID = 2
FUTURE_YEAR_ID = 8

MANUAL_SPLIT_SOURCE_IDS = {1510, 1522, 1658}

# Chỉ cho phép 1 số trường không cộng theo kiểu thông thường.
NETWORK_SINGLE_SCHOOL_KEYS = {"school_count"}
NETWORK_EQUAL_ONLY_KEYS = {"national_standard"}

# Các hậu tố/tiền tố này là chỉ tiêu số lượng có thể cộng khi mọi component đều có số.
NETWORK_SUM_EXACT_KEYS = {
    "class_total",
    "student_total",
    "new_students",
    "staff_total",
    "management_total",
    "teachers",
    "teacher_team",
    "employees_total",
    "rooms_total",
    "rooms_permanent",
    "rooms_semi_permanent",
    "rooms_temporary",
}
NETWORK_SUM_PREFIXES = (
    "grade_",
)
NETWORK_SUM_SUFFIXES = (
    "_classes",
    "_students",
    "_new_students",
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


def table_exists(conn, table):
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,)
    ).fetchone() is not None


def cols(conn, table):
    return [r[1] for r in conn.execute(
        f"PRAGMA table_info({qi(table)})"
    ).fetchall()]


def school(conn, sid):
    return conn.execute(
        "SELECT id,commune_id,code,name,is_active FROM schools WHERE id=?",
        (sid,)
    ).fetchone()


def count_sy(conn, table, sid, year_id):
    return int(conn.execute(
        f"SELECT COUNT(*) FROM {qi(table)} "
        "WHERE school_id=? AND school_year_id=?",
        (sid, year_id)
    ).fetchone()[0])


def dict_rows(conn, table, sid, year_id):
    cur = conn.execute(
        f"SELECT * FROM {qi(table)} "
        "WHERE school_id=? AND school_year_id=? ORDER BY id",
        (sid, year_id)
    )
    names = [d[0] for d in cur.description]
    return [dict(zip(names, r)) for r in cur.fetchall()]


def official_exec_map(conn):
    rows = conn.execute(
        """
        SELECT id,plan_id,operation_id,target_school_id,source_school_ids_json,summary_json
        FROM school_merger_official_executions
        WHERE school_year_id=?
        ORDER BY id
        """,
        (CURRENT_YEAR_ID,)
    ).fetchall()

    m = defaultdict(list)
    for r in rows:
        try:
            src = [int(x) for x in json.loads(r[4] or "[]")]
        except Exception:
            src = []
        try:
            summary = json.loads(r[5] or "{}")
        except Exception:
            summary = {}

        m[int(r[3])].append({
            "id": int(r[0]),
            "plan_id": r[1],
            "operation_id": r[2],
            "target_id": int(r[3]),
            "source_ids": src,
            "summary": summary,
        })
    return m


def is_number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def merge_network_json(payloads):
    """
    Trả (merged, reasons).
    Quy tắc rất chặt:
    - mọi component phải là dict và có cùng key set;
    - school_count => 1;
    - national_standard => chỉ giữ nếu mọi component giống hệt;
    - các chỉ tiêu số lượng => cộng, nhưng cấm mixed NULL/number;
    - key lạ/non-numeric => chỉ giữ nếu tất cả giống hệt; khác nhau thì defer.
    """
    reasons = []
    if not payloads:
        return None, ["NO_PAYLOADS"]

    if not all(isinstance(x, dict) for x in payloads):
        return None, ["PAYLOAD_NOT_OBJECT"]

    keysets = [set(x.keys()) for x in payloads]
    if any(k != keysets[0] for k in keysets[1:]):
        return None, ["KEYSET_MISMATCH"]

    merged = {}
    keys = sorted(keysets[0])

    for key in keys:
        vals = [p.get(key) for p in payloads]

        if key in NETWORK_SINGLE_SCHOOL_KEYS:
            # Mỗi target sau sáp nhập là một trường.
            bad = [v for v in vals if v not in (None, 0, 1)]
            if bad:
                reasons.append(f"{key}:UNEXPECTED={bad}")
            else:
                merged[key] = 1
            continue

        if key in NETWORK_EQUAL_ONLY_KEYS:
            if all(v == vals[0] for v in vals):
                merged[key] = vals[0]
            else:
                reasons.append(f"{key}:CONFLICT={vals}")
            continue

        is_sum_key = (
            key in NETWORK_SUM_EXACT_KEYS
            or key.startswith(NETWORK_SUM_PREFIXES)
            or key.endswith(NETWORK_SUM_SUFFIXES)
        )

        if is_sum_key:
            if all(is_number(v) for v in vals):
                total = sum(vals)
                if all(isinstance(v, int) and not isinstance(v, bool) for v in vals):
                    total = int(total)
                merged[key] = total
            elif all(v is None for v in vals):
                merged[key] = None
            else:
                reasons.append(f"{key}:MIXED_OR_NONNUMERIC={vals}")
            continue

        # Key chưa có quy tắc cộng: chỉ mang qua nếu mọi component giống nhau.
        if all(v == vals[0] for v in vals):
            merged[key] = vals[0]
        else:
            reasons.append(f"{key}:UNSAFE_UNKNOWN_CONFLICT={vals}")

    if reasons:
        return None, reasons
    return merged, []


def prepare_network_plan(conn):
    table = "school_network_year_data"
    exmap = official_exec_map(conn)
    safe = []
    deferred = []

    targets = [
        int(r[0]) for r in conn.execute(
            """
            SELECT DISTINCT school_id
            FROM school_network_year_data
            WHERE school_year_id=?
              AND school_id IN (
                    SELECT target_school_id
                    FROM school_merger_official_executions
                    WHERE school_year_id=?
              )
            ORDER BY school_id
            """,
            (BASE_YEAR_ID, CURRENT_YEAR_ID)
        ).fetchall()
        if count_sy(conn, table, int(r[0]), CURRENT_YEAR_ID) == 0
    ]

    for tid in targets:
        execs = exmap.get(tid, [])
        if len(execs) != 1:
            deferred.append({
                "target_id": tid,
                "school": school(conn, tid),
                "reason": f"OFFICIAL_EXEC_COUNT={len(execs)}",
            })
            continue

        ex = execs[0]
        if tid in MANUAL_SPLIT_SOURCE_IDS:
            deferred.append({
                "target_id": tid,
                "school": school(conn, tid),
                "reason": "MANUAL_SPLIT_SOURCE",
            })
            continue

        component_ids = [tid] + ex["source_ids"]
        grouped = defaultdict(list)

        for sid in component_ids:
            for row in dict_rows(conn, table, sid, BASE_YEAR_ID):
                grouped[str(row["level_code"])].append({
                    "source_school_id": sid,
                    "row": row,
                })

        if len(grouped) != 1:
            deferred.append({
                "target_id": tid,
                "school": school(conn, tid),
                "component_ids": component_ids,
                "reason": "LEVEL_GROUP_COUNT_NOT_1",
                "levels": sorted(grouped),
            })
            continue

        level_code = next(iter(grouped))
        items = grouped[level_code]

        payloads = []
        parse_error = None
        for item in items:
            try:
                p = json.loads(item["row"]["data_json"])
            except Exception as exc:
                parse_error = repr(exc)
                break
            payloads.append(p)

        if parse_error:
            deferred.append({
                "target_id": tid,
                "school": school(conn, tid),
                "component_ids": component_ids,
                "level_code": level_code,
                "reason": "JSON_PARSE_ERROR",
                "details": parse_error,
            })
            continue

        merged, reasons = merge_network_json(payloads)
        if reasons:
            deferred.append({
                "target_id": tid,
                "school": school(conn, tid),
                "component_ids": component_ids,
                "level_code": level_code,
                "reason": "JSON_MERGE_GATE_FAILED",
                "details": reasons,
            })
            continue

        safe.append({
            "target_id": tid,
            "school": school(conn, tid),
            "execution": ex,
            "component_ids": component_ids,
            "level_code": level_code,
            "source_rows": [
                {
                    "source_school_id": x["source_school_id"],
                    "row_id": x["row"]["id"],
                    "source_name": x["row"].get("source_name"),
                }
                for x in items
            ],
            "merged_json": merged,
        })

    return safe, deferred


def make_backup():
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = BACKUP_DIR / f"backup_truoc_BATCH_NGHIEP_VU_11_{ts}.db"

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


def execute_network_target(conn, item):
    tid = int(item["target_id"])
    level = item["level_code"]

    conn.execute("BEGIN IMMEDIATE")
    try:
        if count_sy(conn, "school_network_year_data", tid, CURRENT_YEAR_ID) != 0:
            fail(f"target {tid} vừa xuất hiện dữ liệu y2")

        # Source/component year1 vẫn phải còn nguyên.
        for cid in item["component_ids"]:
            if count_sy(conn, "school_network_year_data", cid, BASE_YEAR_ID) <= 0:
                fail(f"component {cid} mất baseline")

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
        source_desc = ",".join(str(x) for x in item["component_ids"])

        conn.execute(
            """
            INSERT INTO school_network_year_data
            (school_id,school_year_id,level_code,data_json,source_name,imported_at)
            VALUES (?,?,?,?,?,?)
            """,
            (
                tid,
                CURRENT_YEAR_ID,
                level,
                json.dumps(item["merged_json"], ensure_ascii=False, separators=(",", ":")),
                f"Batch 11 - tổng hợp official merger từ school_id {source_desc}",
                now,
            )
        )

        rows = dict_rows(conn, "school_network_year_data", tid, CURRENT_YEAR_ID)
        if len(rows) != 1:
            fail(f"target {tid} y2 row count={len(rows)}")

        check_json = json.loads(rows[0]["data_json"])
        if check_json != item["merged_json"]:
            fail(f"target {tid} JSON post-check mismatch")

        fk = conn.execute("PRAGMA foreign_key_check").fetchall()
        if fk:
            fail(f"target {tid} FK errors {fk[:20]}")

        conn.commit()
        return "COMMIT"

    except Exception:
        conn.rollback()
        raise


def source_audit_for_structured_reports():
    """
    Chỉ đọc mã nguồn, tìm nơi có TH_01_GV / THCS_01_GV để Batch 12
    dùng đúng helper sinh báo cáo từ staff thay vì cộng JSON mù.
    """
    hits = []
    roots = [ROOT / "app"]

    for base in roots:
        if not base.exists():
            continue

        for p in base.rglob("*"):
            if not p.is_file() or p.suffix.lower() not in {".py", ".html", ".jinja2"}:
                continue
            if any(x in p.parts for x in (".venv", "__pycache__", "backups", "exports")):
                continue

            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            lines = text.splitlines()
            for i, line in enumerate(lines):
                if "TH_01_GV" in line or "THCS_01_GV" in line:
                    start = max(0, i - 12)
                    end = min(len(lines), i + 18)
                    hits.append({
                        "file": str(p.relative_to(ROOT)),
                        "line": i + 1,
                        "snippet": "\n".join(
                            f"{j+1:05d}: {lines[j]}" for j in range(start, end)
                        ),
                    })

    REPORT_AUDIT_JSON.write_text(
        json.dumps(hits, ensure_ascii=False, indent=2),
        encoding="utf-8-sig"
    )
    return hits


def audit_remaining(conn):
    remain = []
    exmap = official_exec_map(conn)
    for tid in sorted(exmap):
        if (
            count_sy(conn, "school_network_year_data", tid, BASE_YEAR_ID) > 0
            and count_sy(conn, "school_network_year_data", tid, CURRENT_YEAR_ID) == 0
        ):
            remain.append({
                "target_id": tid,
                "school": school(conn, tid),
                "source_ids": exmap[tid][0]["source_ids"] if len(exmap[tid]) == 1 else [],
            })
    return remain


def main():
    global LOG
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    LOG = OUT.open("w", encoding="utf-8-sig", newline="\n")

    log("=" * 160)
    log("BATCH NGHIỆP VỤ CÒN LẠI TOÀN TỈNH 11")
    log("TỔNG HỢP school_network_year_data CHO MERGER TARGET THEO JSON GATE NGHIÊM NGẶT")
    log("STRUCTURED REPORT: CHỈ RÀ HELPER SOURCE, CHƯA CỘNG JSON TH_01_GV/THCS_01_GV")
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
        fail("DB SHA khác nền Batch 10")

    ro = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True, timeout=60)
    try:
        integ = ro.execute("PRAGMA integrity_check").fetchone()[0]
        fk = ro.execute("PRAGMA foreign_key_check").fetchall()
        log("INTEGRITY_BEFORE =", integ)
        log("FK_BEFORE =", len(fk))
        if integ != "ok" or fk:
            fail("Database health không đạt")

        safe, deferred = prepare_network_plan(ro)
        log("NETWORK_SAFE_TARGET_COUNT =", len(safe))
        log("NETWORK_DEFERRED_TARGET_COUNT =", len(deferred))

        for item in safe:
            log(" NETWORK_SAFE =", json.dumps(item, ensure_ascii=False, default=str))
        for item in deferred:
            log(" NETWORK_DEFERRED =", json.dumps(item, ensure_ascii=False, default=str))

        with NETWORK_DEFERRED_CSV.open("w", encoding="utf-8-sig", newline="") as f:
            fields = ["target_id", "school_code", "school_name", "reason", "details"]
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            for x in deferred:
                s = x.get("school")
                w.writerow({
                    "target_id": x.get("target_id", ""),
                    "school_code": s[2] if s else "",
                    "school_name": s[3] if s else "",
                    "reason": x.get("reason", ""),
                    "details": json.dumps(x, ensure_ascii=False, default=str),
                })
    finally:
        ro.close()

    source_hits = source_audit_for_structured_reports()
    log("STRUCTURED_REPORT_SOURCE_HIT_COUNT =", len(source_hits))
    for x in source_hits[:120]:
        log("\nREPORT_SOURCE_HIT =", x["file"], "LINE", x["line"])
        log(x["snippet"])
    if len(source_hits) > 120:
        log("REPORT_SOURCE_HITS_TRUNCATED =", len(source_hits) - 120)

    if not safe:
        log("NO_WRITE = Không có network target nào qua JSON gate.")
        log("DB_SHA_AFTER =", sha256_file(DB))
        log("BATCH_11_SUCCESS = YES_NO_WRITE")
        if LOG:
            LOG.close()
        return 0

    backup = make_backup()
    log("BACKUP =", backup)
    log("BACKUP_SHA =", sha256_file(backup))

    conn = sqlite3.connect(str(DB), timeout=60)
    conn.execute("PRAGMA foreign_keys=ON")

    results = []
    try:
        for item in safe:
            tid = item["target_id"]
            try:
                status = execute_network_target(conn, item)
                results.append((tid, status, None))
                log("NETWORK_TARGET", tid, "=", status)
            except Exception as exc:
                results.append((tid, "ROLLBACK", repr(exc)))
                log("NETWORK_TARGET", tid, "= ROLLBACK", repr(exc))
                # Tiếp tục target khác theo nguyên tắc transaction độc lập.

        integ = conn.execute("PRAGMA integrity_check").fetchone()[0]
        fk = conn.execute("PRAGMA foreign_key_check").fetchall()
        remaining = audit_remaining(conn)

        log("\n" + "=" * 160)
        log("POST VERIFY BATCH 11")
        log("=" * 160)
        log("INTEGRITY_AFTER =", integ)
        log("FK_AFTER =", len(fk))
        log("RESULTS =", results)
        log("NETWORK_REMAINING_OFFICIAL_TARGET_COUNT =", len(remaining))
        for x in remaining:
            log(" REMAINING_NETWORK =", json.dumps(x, ensure_ascii=False, default=str))
        log("NETWORK_DEFERRED_CSV =", NETWORK_DEFERRED_CSV)
        log("STRUCTURED_REPORT_SOURCE_AUDIT =", REPORT_AUDIT_JSON)
        log("DB_SHA_AFTER =", sha256_file(DB))

        if integ != "ok" or fk:
            fail("Post verify Batch 11 không đạt")

        log("STRUCTURED_REPORT_POLICY = Không cộng TH_01_GV/THCS_01_GV bằng suy đoán; Batch 12 dùng helper/source vừa rà để sinh lại từ dữ liệu đội ngũ hiện hành nếu có.")
        log("MANUAL_SPLIT_1510_1522_1658 = GIỮ MANUAL.")
        log("BATCH_11_SUCCESS = YES")
        log("NEXT_STAGE = Batch 12 tái sinh structured report inputs cho merger target từ staff hiện hành bằng đúng logic source code; không ghi đè JSON bằng phép cộng mù.")
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
            log("BATCH_11_SUCCESS = NO")
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
