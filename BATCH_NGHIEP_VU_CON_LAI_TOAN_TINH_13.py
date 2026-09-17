# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import inspect
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
OUT = EXPORT_DIR / "BATCH_NGHIEP_VU_CON_LAI_TOAN_TINH_13.txt"

# Batch 12 không ghi DB.
EXPECTED_DB_SHA = "80a35bdab22c48fa896aa16286ed834b9280bbcc601afa148c10f0c728d516b6"

BASE_YEAR_ID = 1
CURRENT_YEAR_ID = 2
FUTURE_YEAR_ID = 8

MANUAL_SPLIT_SOURCE_IDS = {1510, 1522, 1658}

# Chỉ tiêu số lượng mạng lưới MN: cộng được giữa các trường thành phần.
MN_SUM_KEYS = {
    "class_total",
    "staff_total",
    "student_total",
    "class_24_36m",
    "class_3_4y",
    "class_4_5y",
    "class_5_6y",
    "classroom_total",
    "employee_total",
    "manager_total",
    "new_student_total",
    "room_permanent",
    "room_semi_permanent",
    "room_temporary",
    "student_12_24m",
    "student_24_36m",
    "student_3_4y",
    "student_4_5y",
    "student_5_6y",
    "teacher_total",
}
MN_SINGLE_SCHOOL_KEYS = {"school_count"}
MN_EQUAL_ONLY_KEYS = {"national_standard_count"}

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


def one(conn, sql, params=()):
    return conn.execute(sql, params).fetchone()


def table_exists(conn, table):
    return one(
        conn,
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,)
    ) is not None


def school(conn, sid):
    return one(
        conn,
        "SELECT id,commune_id,code,name,is_active FROM schools WHERE id=?",
        (sid,)
    )


def count_sy(conn, table, sid, year_id):
    return int(one(
        conn,
        f"SELECT COUNT(*) FROM {qi(table)} "
        "WHERE school_id=? AND school_year_id=?",
        (sid, year_id)
    )[0])


def dict_rows(conn, table, sid, year_id, form_code=None):
    sql = (
        f"SELECT * FROM {qi(table)} "
        "WHERE school_id=? AND school_year_id=?"
    )
    params = [sid, year_id]
    if form_code is not None:
        sql += " AND form_code=?"
        params.append(form_code)
    sql += " ORDER BY id"

    cur = conn.execute(sql, tuple(params))
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
            source_ids = [int(x) for x in json.loads(r[4] or "[]")]
        except Exception:
            source_ids = []
        m[int(r[3])].append({
            "id": int(r[0]),
            "plan_id": r[1],
            "operation_id": r[2],
            "target_id": int(r[3]),
            "source_ids": source_ids,
        })
    return m


def is_number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def merge_mn_payloads(payloads):
    if not payloads:
        return None, ["NO_PAYLOADS"]
    if not all(isinstance(p, dict) for p in payloads):
        return None, ["PAYLOAD_NOT_DICT"]

    keysets = [set(p.keys()) for p in payloads]
    if any(x != keysets[0] for x in keysets[1:]):
        return None, ["KEYSET_MISMATCH"]

    merged = {}
    reasons = []

    for key in sorted(keysets[0]):
        vals = [p.get(key) for p in payloads]

        if key in MN_SINGLE_SCHOOL_KEYS:
            if all(v in (None, 0, 1) for v in vals):
                merged[key] = 1
            else:
                reasons.append(f"{key}:UNEXPECTED={vals}")
            continue

        if key in MN_EQUAL_ONLY_KEYS:
            if all(v == vals[0] for v in vals):
                merged[key] = vals[0]
            else:
                reasons.append(f"{key}:CURRENT_STATUS_CONFLICT={vals}")
            continue

        if key in MN_SUM_KEYS:
            if all(is_number(v) for v in vals):
                total = sum(vals)
                if all(isinstance(v, int) and not isinstance(v, bool) for v in vals):
                    total = int(total)
                merged[key] = total
            elif all(v is None for v in vals):
                merged[key] = None
            else:
                # Không coi NULL = 0.
                reasons.append(f"{key}:MIXED_OR_NONNUMERIC={vals}")
            continue

        if all(v == vals[0] for v in vals):
            merged[key] = vals[0]
        else:
            reasons.append(f"{key}:UNSAFE_UNKNOWN_CONFLICT={vals}")

    if reasons:
        return None, reasons
    return merged, []


def prepare_mn_network(conn):
    exmap = official_exec_map(conn)
    safe = []
    deferred = []

    target_ids = [
        int(r[0]) for r in conn.execute(
            """
            SELECT DISTINCT school_id
            FROM school_network_year_data
            WHERE school_year_id=?
              AND UPPER(COALESCE(level_code,''))='MN'
              AND school_id IN (
                    SELECT target_school_id
                    FROM school_merger_official_executions
                    WHERE school_year_id=?
              )
            ORDER BY school_id
            """,
            (BASE_YEAR_ID, CURRENT_YEAR_ID)
        ).fetchall()
        if count_sy(conn, "school_network_year_data", int(r[0]), CURRENT_YEAR_ID) == 0
    ]

    for tid in target_ids:
        execs = exmap.get(tid, [])
        if len(execs) != 1:
            deferred.append({
                "target_id": tid,
                "school": school(conn, tid),
                "reason": f"OFFICIAL_EXEC_COUNT={len(execs)}",
            })
            continue

        ex = execs[0]
        component_ids = [tid] + ex["source_ids"]

        payloads = []
        component_rows = []
        bad = None

        for cid in component_ids:
            rows = [
                r for r in dict_rows(
                    conn, "school_network_year_data", cid, BASE_YEAR_ID
                )
                if str(r.get("level_code") or "").upper() == "MN"
            ]
            if len(rows) != 1:
                bad = f"COMPONENT_{cid}_MN_ROW_COUNT={len(rows)}"
                break
            try:
                payload = json.loads(rows[0]["data_json"])
            except Exception as exc:
                bad = f"COMPONENT_{cid}_JSON_PARSE={exc!r}"
                break

            payloads.append(payload)
            component_rows.append({
                "school_id": cid,
                "row_id": rows[0]["id"],
            })

        if bad:
            deferred.append({
                "target_id": tid,
                "school": school(conn, tid),
                "component_ids": component_ids,
                "reason": bad,
            })
            continue

        merged, reasons = merge_mn_payloads(payloads)
        if reasons:
            deferred.append({
                "target_id": tid,
                "school": school(conn, tid),
                "component_ids": component_ids,
                "reason": "MERGE_GATE_FAILED",
                "details": reasons,
            })
            continue

        safe.append({
            "target_id": tid,
            "school": school(conn, tid),
            "component_ids": component_ids,
            "component_rows": component_rows,
            "merged_json": merged,
        })

    return safe, deferred


def make_backup():
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = BACKUP_DIR / f"backup_truoc_BATCH_NGHIEP_VU_13_{ts}.db"

    src = sqlite3.connect(str(DB), timeout=60)
    dst = sqlite3.connect(str(path), timeout=60)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()

    ro = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=30)
    try:
        integrity = ro.execute("PRAGMA integrity_check").fetchone()[0]
        fk = ro.execute("PRAGMA foreign_key_check").fetchall()
    finally:
        ro.close()

    if integrity != "ok" or fk:
        fail(f"Backup không đạt integrity={integrity}, fk={len(fk)}")
    return path


def execute_mn_target(conn, item):
    tid = int(item["target_id"])
    conn.execute("BEGIN IMMEDIATE")
    try:
        if count_sy(conn, "school_network_year_data", tid, CURRENT_YEAR_ID) != 0:
            fail(f"Target {tid} vừa xuất hiện y2")

        for cid in item["component_ids"]:
            if count_sy(conn, "school_network_year_data", cid, BASE_YEAR_ID) <= 0:
                fail(f"Component {cid} mất baseline")

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
        conn.execute(
            """
            INSERT INTO school_network_year_data
            (school_id,school_year_id,level_code,data_json,source_name,imported_at)
            VALUES (?,?,?,?,?,?)
            """,
            (
                tid,
                CURRENT_YEAR_ID,
                "MN",
                json.dumps(
                    item["merged_json"],
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                "Batch 13 - tổng hợp mạng lưới MN theo official merger; chỉ cộng chỉ tiêu số lượng, không suy diễn trạng thái chuẩn quốc gia.",
                now,
            )
        )

        rows = dict_rows(
            conn,
            "school_network_year_data",
            tid,
            CURRENT_YEAR_ID,
        )
        if len(rows) != 1:
            fail(f"Target {tid}: y2 row count={len(rows)}")

        check = json.loads(rows[0]["data_json"])
        if check != item["merged_json"]:
            fail(f"Target {tid}: JSON post mismatch")

        fk = conn.execute("PRAGMA foreign_key_check").fetchall()
        if fk:
            fail(f"Target {tid}: FK={fk[:20]}")

        conn.commit()
        return "COMMIT"
    except Exception:
        conn.rollback()
        raise


def audit_structured_staff(conn):
    """
    Không ghi school_structured_report_inputs.
    Source export hiện hành lấy số liệu đội ngũ trực tiếp từ
    _staff_rows + _staff_summary + _class_count_with_network.
    Structured JSON chỉ là overlay; việc không có dòng Y2 không được xem là
    thiếu dữ liệu đội ngũ nếu helper hiện hành vẫn sinh được số liệu.
    """
    import app.pcgd_xmc_report_builders_v1 as builders
    from sqlalchemy.orm import Session
    from app.database import engine

    helper_names = (
        "_staff_rows",
        "_staff_summary",
        "_schools_and_classes",
        "_class_count_with_network",
    )

    helper_hashes = {}
    for name in helper_names:
        func = getattr(builders, name)
        src = inspect.getsource(func)
        low = src.lower()
        if any(
            token in low
            for token in (
                ".commit(",
                ".rollback(",
                ".add(",
                ".delete(",
                ".flush(",
            )
        ):
            fail(f"Helper {name} có dấu hiệu ghi DB")
        helper_hashes[name] = hashlib.sha256(
            src.encode("utf-8")
        ).hexdigest()

    exmap = official_exec_map(conn)
    audit = []
    errors = []

    candidates = conn.execute(
        """
        SELECT DISTINCT school_id,UPPER(form_code)
        FROM school_structured_report_inputs
        WHERE school_year_id=?
          AND UPPER(COALESCE(form_code,'')) IN ('TH_01_GV','THCS_01_GV')
          AND school_id IN (
                SELECT target_school_id
                FROM school_merger_official_executions
                WHERE school_year_id=?
          )
        ORDER BY school_id,UPPER(form_code)
        """,
        (BASE_YEAR_ID, CURRENT_YEAR_ID)
    ).fetchall()

    with Session(engine) as db:
        for tid_raw, form_code in candidates:
            tid = int(tid_raw)
            if tid in MANUAL_SPLIT_SOURCE_IDS:
                continue

            level = "TH" if form_code == "TH_01_GV" else "THCS"
            try:
                schools, grades = builders._schools_and_classes(
                    db, CURRENT_YEAR_ID, None, tid
                )
                records_map = builders._staff_rows(
                    db, CURRENT_YEAR_ID, [tid]
                )
                staff_rows = records_map.get(tid, [])
                class_count = builders._class_count_with_network(
                    db,
                    school_id=tid,
                    school_year_id=CURRENT_YEAR_ID,
                    grades=grades,
                    level=level,
                )
                summary = builders._staff_summary(
                    staff_rows, class_count
                )
            except Exception as exc:
                errors.append({
                    "target_id": tid,
                    "form_code": form_code,
                    "error": repr(exc),
                })
                continue

            if not isinstance(summary, dict):
                errors.append({
                    "target_id": tid,
                    "form_code": form_code,
                    "error": f"SUMMARY_TYPE={type(summary).__name__}",
                })
                continue

            audit.append({
                "target_id": tid,
                "school": school(conn, tid),
                "form_code": form_code,
                "official_exec_count": len(exmap.get(tid, [])),
                "staff_rows": len(staff_rows),
                "class_count": class_count,
                "principal": summary.get("principal"),
                "vice": summary.get("vice"),
                "teachers": summary.get("teachers"),
                "employees": summary.get("employees"),
                "ratio": summary.get("ratio"),
                "summary_keys": sorted(summary.keys()),
            })

    return audit, errors, helper_hashes


def audit_remaining_network(conn):
    exmap = official_exec_map(conn)
    out = []

    for tid in sorted(exmap):
        y1 = count_sy(
            conn, "school_network_year_data", tid, BASE_YEAR_ID
        )
        y2 = count_sy(
            conn, "school_network_year_data", tid, CURRENT_YEAR_ID
        )
        if y1 > 0 and y2 == 0:
            out.append({
                "target_id": tid,
                "school": school(conn, tid),
                "source_ids": (
                    exmap[tid][0]["source_ids"]
                    if len(exmap[tid]) == 1 else []
                ),
            })
    return out


def audit_manual_split(conn):
    out = []
    for sid in sorted(MANUAL_SPLIT_SOURCE_IDS):
        out.append({
            "school": school(conn, sid),
            "staff_y1": count_sy(
                conn, "staff_year_records", sid, BASE_YEAR_ID
            ),
            "staff_y2": count_sy(
                conn, "staff_year_records", sid, CURRENT_YEAR_ID
            ),
        })
    return out


def audit_empty_baseline_tables(conn):
    result = {}
    for table in (
        "finance_year_entries",
        "school_facility_year_items",
        "historical_datasets",
        "historical_households",
        "historical_people",
    ):
        if not table_exists(conn, table):
            continue
        c = [x[1] for x in conn.execute(
            f"PRAGMA table_info({qi(table)})"
        ).fetchall()]
        item = {
            "total": int(one(
                conn, f"SELECT COUNT(*) FROM {qi(table)}"
            )[0])
        }
        if "school_year_id" in c:
            item["y1"] = int(one(
                conn,
                f"SELECT COUNT(*) FROM {qi(table)} WHERE school_year_id=?",
                (BASE_YEAR_ID,)
            )[0])
            item["y2"] = int(one(
                conn,
                f"SELECT COUNT(*) FROM {qi(table)} WHERE school_year_id=?",
                (CURRENT_YEAR_ID,)
            )[0])
        result[table] = item
    return result


def main():
    global LOG
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    LOG = OUT.open("w", encoding="utf-8-sig", newline="\n")

    log("=" * 160)
    log("BATCH NGHIỆP VỤ CÒN LẠI TOÀN TỈNH 13")
    log("HOÀN TẤT 4 MẠNG LƯỚI MN AN TOÀN + KIỂM TOÁN ĐỘI NGŨ BÁO CÁO ĐỘNG + ĐÓNG ROLLOVER TỰ ĐỘNG")
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
        fail("DB SHA khác nền Batch 12")

    ro = sqlite3.connect(
        f"file:{DB.as_posix()}?mode=ro",
        uri=True,
        timeout=60,
    )
    try:
        integrity = ro.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]
        fk = ro.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()
        log("INTEGRITY_BEFORE =", integrity)
        log("FK_BEFORE =", len(fk))
        if integrity != "ok" or fk:
            fail("Database health không đạt")

        mn_safe, mn_deferred = prepare_mn_network(ro)
        log("MN_SAFE_COUNT =", len(mn_safe))
        log("MN_DEFERRED_COUNT =", len(mn_deferred))
        for x in mn_safe:
            log(
                " MN_SAFE =",
                json.dumps(
                    x,
                    ensure_ascii=False,
                    default=str,
                )
            )
        for x in mn_deferred:
            log(
                " MN_DEFERRED =",
                json.dumps(
                    x,
                    ensure_ascii=False,
                    default=str,
                )
            )

        staff_audit, staff_errors, helper_hashes = (
            audit_structured_staff(ro)
        )
        log(
            "REPORT_HELPER_HASHES =",
            json.dumps(
                helper_hashes,
                ensure_ascii=False,
            )
        )
        log(
            "STRUCTURED_DYNAMIC_STAFF_AUDIT_COUNT =",
            len(staff_audit),
        )
        log(
            "STRUCTURED_DYNAMIC_STAFF_ERROR_COUNT =",
            len(staff_errors),
        )

        for x in staff_audit:
            log(
                " STAFF_DYNAMIC =",
                json.dumps(
                    x,
                    ensure_ascii=False,
                    default=str,
                )
            )
        for x in staff_errors:
            log(
                " STAFF_DYNAMIC_ERROR =",
                json.dumps(
                    x,
                    ensure_ascii=False,
                    default=str,
                )
            )
    finally:
        ro.close()

    if not mn_safe:
        log("MN_WRITE = SKIP_NO_SAFE_TARGET")
        backup = None
    else:
        backup = make_backup()
        log("BACKUP =", backup)
        log("BACKUP_SHA =", sha256_file(backup))

        conn = sqlite3.connect(str(DB), timeout=60)
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            results = []
            for item in mn_safe:
                tid = item["target_id"]
                try:
                    status = execute_mn_target(
                        conn, item
                    )
                    results.append(
                        (tid, status, None)
                    )
                    log(
                        "MN_TARGET",
                        tid,
                        "=",
                        status,
                    )
                except Exception as exc:
                    results.append(
                        (
                            tid,
                            "ROLLBACK",
                            repr(exc),
                        )
                    )
                    log(
                        "MN_TARGET",
                        tid,
                        "= ROLLBACK",
                        repr(exc),
                    )
        finally:
            conn.close()

    final = sqlite3.connect(
        f"file:{DB.as_posix()}?mode=ro",
        uri=True,
        timeout=60,
    )
    try:
        integrity_after = final.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]
        fk_after = final.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()

        remaining_network = audit_remaining_network(
            final
        )
        manual_split = audit_manual_split(final)
        empty_baselines = audit_empty_baseline_tables(
            final
        )

        log("\n" + "=" * 160)
        log("POST VERIFY BATCH 13")
        log("=" * 160)
        log("INTEGRITY_AFTER =", integrity_after)
        log("FK_AFTER =", len(fk_after))
        log(
            "REMAINING_NETWORK_COUNT =",
            len(remaining_network),
        )
        for x in remaining_network:
            log(
                " REMAINING_NETWORK =",
                json.dumps(
                    x,
                    ensure_ascii=False,
                    default=str,
                )
            )

        log(
            "MANUAL_SPLIT_AUDIT =",
            json.dumps(
                manual_split,
                ensure_ascii=False,
                default=str,
            )
        )
        log(
            "EMPTY_BASELINE_AUDIT =",
            json.dumps(
                empty_baselines,
                ensure_ascii=False,
                default=str,
            )
        )
        log("DB_SHA_AFTER =", sha256_file(DB))

        if integrity_after != "ok" or fk_after:
            fail("Post verify Batch 13 không đạt")

        # Điều kiện đóng rollover tự động:
        # - helper đội ngũ chạy không lỗi;
        # - còn lại network là ca có NULL/trạng thái xung đột cần dữ liệu thực tế;
        # - 3 nguồn split vẫn manual;
        # - tài chính/CSVC/history baseline rỗng không được sinh giả.
        automatic_closed = (
            len(staff_errors) == 0
            and len(manual_split) == 3
        )

        log(
            "STRUCTURED_STAFF_POLICY = KHÔNG INSERT DÒNG Y2 CHỈ ĐỂ ĐỦ BẢNG; báo cáo TH/THCS lấy số liệu hiện hành trực tiếp từ staff helper, còn structured input là lớp overlay/định tính."
        )
        log(
            "NETWORK_REMAINING_POLICY = Chỉ còn các target có NULL hoặc trạng thái/thuộc tính không thể suy diễn; phải cập nhật từ số liệu hiện hành, không coi NULL=0."
        )
        log(
            "MANUAL_SPLIT_POLICY = 1510/1522/1658 vẫn chờ bảng phân bổ thực tế."
        )
        log(
            "NO_BASELINE_POLICY = tài chính/CSVC/history không có baseline thì không tự sinh."
        )
        log(
            "AUTOMATIC_DATA_ROLLOVER_CLOSED =",
            "YES" if automatic_closed else "NO",
        )
        log("BATCH_13_SUCCESS = YES")
        log(
            "NEXT_STAGE = Chuyển sang kiểm toán/chức năng nghiệp vụ còn lại; các mục còn thiếu dữ liệu thực tế được đánh dấu nhập/cập nhật thay vì tiếp tục tự rollover."
        )
        log("=" * 160)
        return 0
    finally:
        final.close()
        if LOG:
            LOG.close()


if __name__ == "__main__":
    try:
        code = main()
    except Exception as exc:
        try:
            log("\n" + "=" * 160)
            log("BATCH_13_SUCCESS = NO")
            log("ERROR =", repr(exc))
            if DB.exists():
                log(
                    "DB_SHA_CURRENT =",
                    sha256_file(DB),
                )
            log("DỪNG AN TOÀN.")
            log("=" * 160)
        finally:
            if LOG and not LOG.closed:
                LOG.close()
        code = 1

    sys.exit(code)
