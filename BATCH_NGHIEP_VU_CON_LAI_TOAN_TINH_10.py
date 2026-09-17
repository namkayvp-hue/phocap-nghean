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

OUT = EXPORT_DIR / "BATCH_NGHIEP_VU_CON_LAI_TOAN_TINH_10.txt"
DEFERRED_CSV = EXPORT_DIR / "BATCH_10_MERGER_TARGET_DEFERRED.csv"
JSON_AUDIT = EXPORT_DIR / "BATCH_10_JSON_COLLISION_AUDIT.json"

# Nền ngay sau Batch 09.
EXPECTED_DB_SHA = "38dd4f8c5e4ebfe9a317eda485912b6eb7d985ce31331ca7c9a426ec74c28a7e"

BASE_YEAR_ID = 1
CURRENT_YEAR_ID = 2
FUTURE_YEAR_ID = 8

MANUAL_SPLIT_SOURCE_IDS = {1510, 1522, 1658}

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


def one(conn, sql, params=()):
    return conn.execute(sql, params).fetchone()


def all_rows(conn, sql, params=()):
    return conn.execute(sql, params).fetchall()


def school(conn, sid):
    return one(
        conn,
        "SELECT id,commune_id,code,name,is_active FROM schools WHERE id=?",
        (sid,)
    )


def count_school_year(conn, table, sid, year_id):
    return int(one(
        conn,
        f"SELECT COUNT(*) FROM {qi(table)} "
        "WHERE school_id=? AND school_year_id=?",
        (sid, year_id)
    )[0])


def read_dict_rows(conn, table, sid, year_id):
    cur = conn.execute(
        f"SELECT * FROM {qi(table)} "
        "WHERE school_id=? AND school_year_id=? "
        + ("ORDER BY id" if "id" in cols(conn, table) else ""),
        (sid, year_id)
    )
    names = [d[0] for d in cur.description]
    return [dict(zip(names, r)) for r in cur.fetchall()]


def official_executions(conn):
    rows = all_rows(
        conn,
        """
        SELECT id,plan_id,operation_id,target_school_id,source_school_ids_json,summary_json
        FROM school_merger_official_executions
        WHERE school_year_id=?
        ORDER BY id
        """,
        (CURRENT_YEAR_ID,)
    )
    out = []
    for r in rows:
        try:
            src = [int(x) for x in json.loads(r[4] or "[]")]
        except Exception:
            src = []
        try:
            summary = json.loads(r[5] or "{}")
        except Exception:
            summary = {}
        out.append({
            "id": int(r[0]),
            "plan_id": r[1],
            "operation_id": r[2],
            "target_school_id": int(r[3]),
            "source_ids": src,
            "summary": summary,
        })
    return out


def execution_map(conn):
    m = defaultdict(list)
    for ex in official_executions(conn):
        m[ex["target_school_id"]].append(ex)
    return m


def old_rows_hash(conn, table):
    if "id" not in cols(conn, table):
        return None
    max_id = int(one(
        conn,
        f"SELECT COALESCE(MAX(id),0) FROM {qi(table)}"
    )[0])
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
    now_hash = hashlib.sha256(
        json.dumps(rows, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    return old_hash == now_hash


def make_backup():
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = BACKUP_DIR / f"backup_truoc_BATCH_NGHIEP_VU_10_{ts}.db"

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


def prepare_mn01_plan(conn, exmap):
    table = "school_mn01_gv_inputs"
    plan = {"safe": [], "deferred": []}
    if not table_exists(conn, table):
        return plan

    targets = [
        int(r[0]) for r in all_rows(
            conn,
            f"""
            SELECT DISTINCT school_id
            FROM {qi(table)}
            WHERE school_year_id=?
              AND school_id IN (
                    SELECT target_school_id
                    FROM school_merger_official_executions
                    WHERE school_year_id=?
              )
            ORDER BY school_id
            """,
            (BASE_YEAR_ID, CURRENT_YEAR_ID)
        )
        if count_school_year(conn, table, int(r[0]), CURRENT_YEAR_ID) == 0
    ]

    for tid in targets:
        execs = exmap.get(tid, [])
        if len(execs) != 1:
            plan["deferred"].append({
                "table": table, "target_id": tid,
                "reason": f"OFFICIAL_EXEC_COUNT={len(execs)}"
            })
            continue

        ex = execs[0]
        if tid in MANUAL_SPLIT_SOURCE_IDS:
            plan["deferred"].append({
                "table": table, "target_id": tid,
                "reason": "MANUAL_SPLIT_SOURCE"
            })
            continue

        component_ids = [tid] + ex["source_ids"]
        rows = []
        missing = []

        for sid in component_ids:
            rr = read_dict_rows(conn, table, sid, BASE_YEAR_ID)
            if len(rr) != 1:
                missing.append((sid, len(rr), school(conn, sid)))
            else:
                rows.append((sid, rr[0]))

        if missing:
            plan["deferred"].append({
                "table": table, "target_id": tid,
                "reason": "COMPONENT_BASE_ROW_NOT_EXACTLY_ONE",
                "details": missing,
                "component_ids": component_ids,
            })
            continue

        total_ethnic = sum(int(r.get("ethnic_staff_count") or 0) for _, r in rows)
        plan["safe"].append({
            "table": table,
            "target_id": tid,
            "target_school": school(conn, tid),
            "execution": ex,
            "component_ids": component_ids,
            "ethnic_staff_count": total_ethnic,
        })

    return plan


def execute_mn01(conn, plan):
    table = "school_mn01_gv_inputs"
    safe = plan["safe"]
    if not safe:
        log("MN01_GV_AGG = SKIP_NO_SAFE_TARGET")
        return {"status": "SKIP", "inserted": 0}

    baseline = old_rows_hash(conn, table)
    conn.execute("BEGIN IMMEDIATE")
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
        created = 0

        for item in safe:
            tid = item["target_id"]
            if count_school_year(conn, table, tid, CURRENT_YEAR_ID) != 0:
                fail(f"MN01 target {tid} vừa xuất hiện y2")

            conn.execute(
                """
                INSERT INTO school_mn01_gv_inputs
                (school_id,school_year_id,ethnic_staff_count,notes,updated_by_user_id,updated_at)
                VALUES (?,?,?,?,?,?)
                """,
                (
                    tid,
                    CURRENT_YEAR_ID,
                    item["ethnic_staff_count"],
                    "Tổng hợp nền 2026-2027 từ trường đích và các trường nguồn theo official merger; ethnic_staff_count được cộng vì là chỉ tiêu số lượng.",
                    None,
                    now,
                )
            )
            created += 1

        if created != len(safe):
            fail("MN01 created != safe")

        if not verify_old_rows_hash(conn, table, baseline):
            fail("MN01 old rows changed")

        for item in safe:
            if count_school_year(conn, table, item["target_id"], CURRENT_YEAR_ID) != 1:
                fail(f"MN01 post-count target={item['target_id']}")

        fk = conn.execute("PRAGMA foreign_key_check").fetchall()
        if fk:
            fail(f"MN01 FK errors {fk[:20]}")

        conn.commit()
        log("MN01_GV_AGG_COMMIT = YES")
        log("MN01_GV_AGG_INSERTED =", created)
        return {"status": "COMMIT", "inserted": created}

    except Exception:
        conn.rollback()
        log("MN01_GV_AGG_ROLLBACK = YES")
        raise


def plan_unique_component_rows(conn, table, key_col, exmap):
    """
    Chỉ carry forward khi mỗi key (level_code/form_code) xuất hiện ở đúng 1 component
    trong target + source. Nếu cùng key xuất hiện ở 2 trường trở lên => cần quy tắc merge
    data_json riêng, tuyệt đối không tự cộng/ghi đè.
    """
    plan = {"safe": [], "deferred": [], "audit": []}

    missing_targets = [
        int(r[0]) for r in all_rows(
            conn,
            f"""
            SELECT DISTINCT school_id
            FROM {qi(table)}
            WHERE school_year_id=?
              AND school_id IN (
                    SELECT target_school_id
                    FROM school_merger_official_executions
                    WHERE school_year_id=?
              )
            ORDER BY school_id
            """,
            (BASE_YEAR_ID, CURRENT_YEAR_ID)
        )
        if count_school_year(conn, table, int(r[0]), CURRENT_YEAR_ID) == 0
    ]

    for tid in missing_targets:
        execs = exmap.get(tid, [])
        if len(execs) != 1:
            plan["deferred"].append({
                "table": table, "target_id": tid,
                "reason": f"OFFICIAL_EXEC_COUNT={len(execs)}"
            })
            continue

        ex = execs[0]
        component_ids = [tid] + ex["source_ids"]
        groups = defaultdict(list)

        for sid in component_ids:
            for row in read_dict_rows(conn, table, sid, BASE_YEAR_ID):
                key = row.get(key_col)
                groups[str(key)].append({
                    "component_school_id": sid,
                    "row": row,
                })

        collisions = {
            k: [x["component_school_id"] for x in v]
            for k, v in groups.items()
            if len(v) > 1
        }

        plan["audit"].append({
            "table": table,
            "target_id": tid,
            "component_ids": component_ids,
            "keys": sorted(groups),
            "collisions": collisions,
        })

        if collisions:
            plan["deferred"].append({
                "table": table,
                "target_id": tid,
                "target_school": school(conn, tid),
                "reason": f"DUPLICATE_{key_col.upper()}_ACROSS_COMPONENTS",
                "component_ids": component_ids,
                "collisions": collisions,
            })
            continue

        # Không có collision: mỗi key đến từ đúng 1 component nên có thể carry nguyên JSON.
        carry = []
        for key in sorted(groups):
            item = groups[key][0]
            carry.append({
                "source_component_id": item["component_school_id"],
                "row": item["row"],
            })

        if not carry:
            plan["deferred"].append({
                "table": table,
                "target_id": tid,
                "target_school": school(conn, tid),
                "reason": "NO_BASE_ROWS_IN_ANY_COMPONENT",
                "component_ids": component_ids,
            })
            continue

        plan["safe"].append({
            "table": table,
            "target_id": tid,
            "target_school": school(conn, tid),
            "execution": ex,
            "component_ids": component_ids,
            "carry_rows": carry,
        })

    return plan


def clone_component_rows(conn, table, plan):
    safe = plan["safe"]
    if not safe:
        log(table, "CARRY = SKIP_NO_SAFE_TARGET")
        return {"status": "SKIP", "inserted": 0}

    info = table_info(conn, table)
    insert_cols = [r[1] for r in info if r[1] != "id"]
    sql = (
        f"INSERT INTO {qi(table)} "
        f"({', '.join(qi(c) for c in insert_cols)}) "
        f"VALUES ({', '.join('?' for _ in insert_cols)})"
    )

    baseline = old_rows_hash(conn, table)
    conn.execute("BEGIN IMMEDIATE")
    try:
        created = 0
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")

        for item in safe:
            tid = item["target_id"]
            if count_school_year(conn, table, tid, CURRENT_YEAR_ID) != 0:
                fail(f"{table}: target {tid} vừa có y2")

            for citem in item["carry_rows"]:
                d = dict(citem["row"])
                d["school_id"] = tid
                d["school_year_id"] = CURRENT_YEAR_ID

                if "updated_by_user_id" in d:
                    d["updated_by_user_id"] = None
                if "updated_at" in d:
                    d["updated_at"] = now

                # network_year_data không có updated_at; imported_at giữ nguyên để bảo toàn provenance.
                conn.execute(sql, [d.get(c) for c in insert_cols])
                created += 1

        if not verify_old_rows_hash(conn, table, baseline):
            fail(f"{table}: old rows changed")

        # mỗi target phải có đúng số carry row.
        for item in safe:
            actual = count_school_year(conn, table, item["target_id"], CURRENT_YEAR_ID)
            expected = len(item["carry_rows"])
            if actual != expected:
                fail(
                    f"{table}: target={item['target_id']} "
                    f"actual={actual} expected={expected}"
                )

        fk = conn.execute("PRAGMA foreign_key_check").fetchall()
        if fk:
            fail(f"{table}: FK errors {fk[:20]}")

        conn.commit()
        log(table, "CARRY_COMMIT = YES")
        log(table, "CARRY_INSERTED =", created)
        return {
            "status": "COMMIT",
            "inserted": created,
            "target_count": len(safe),
        }

    except Exception:
        conn.rollback()
        log(table, "CARRY_ROLLBACK = YES")
        raise


def audit_nonbaseline_modules(conn):
    audit = {}

    def tbl_count(table, where="", params=()):
        sql = f"SELECT COUNT(*) FROM {qi(table)}"
        if where:
            sql += " WHERE " + where
        return int(one(conn, sql, params)[0])

    for table in (
        "finance_year_entries",
        "school_facility_year_items",
        "historical_datasets",
        "historical_households",
        "historical_people",
        "survey_person_year_disability_types",
        "student_survey_comparison_signoffs",
        "student_survey_resolution_logs",
    ):
        if not table_exists(conn, table):
            continue
        audit[table] = {"total": tbl_count(table)}
        if "school_year_id" in cols(conn, table):
            audit[table]["y1"] = tbl_count(
                table, "school_year_id=?", (BASE_YEAR_ID,)
            )
            audit[table]["y2"] = tbl_count(
                table, "school_year_id=?", (CURRENT_YEAR_ID,)
            )

    # Khuyết tật đang được lưu trực tiếp trong survey_person_year_records.
    if table_exists(conn, "survey_person_year_records"):
        audit["survey_person_year_records_disability"] = {
            "y2_total": tbl_count(
                "survey_person_year_records",
                "school_year_id=?",
                (CURRENT_YEAR_ID,)
            ),
            "status_filled": tbl_count(
                "survey_person_year_records",
                "school_year_id=? AND TRIM(COALESCE(disability_status,''))<>''",
                (CURRENT_YEAR_ID,)
            ),
            "type_filled": tbl_count(
                "survey_person_year_records",
                "school_year_id=? AND TRIM(COALESCE(disability_type,''))<>''",
                (CURRENT_YEAR_ID,)
            ),
        }

    if table_exists(conn, "student_reconciliation_source_states"):
        rows = all_rows(
            conn,
            """
            SELECT id,target_school_year_id,source_school_year_id,commune_id,status,
                   total_rows,valid_rows,student_count,enrollment_count,class_count,import_count
            FROM student_reconciliation_source_states
            ORDER BY id
            """
        )
        audit["student_reconciliation_source_states"] = rows

    return audit


def final_remaining(conn, table):
    rows = []
    exmap = execution_map(conn)
    for tid, execs in sorted(exmap.items()):
        if count_school_year(conn, table, tid, BASE_YEAR_ID) > 0 \
                and count_school_year(conn, table, tid, CURRENT_YEAR_ID) == 0:
            rows.append({
                "target_id": tid,
                "school": school(conn, tid),
                "exec_count": len(execs),
                "source_ids": execs[0]["source_ids"] if len(execs) == 1 else [],
            })
    return rows


def main():
    global LOG
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    LOG = OUT.open("w", encoding="utf-8-sig", newline="\n")

    log("=" * 160)
    log("BATCH NGHIỆP VỤ CÒN LẠI TOÀN TỈNH 10")
    log("MERGER TARGET: TỔNG HỢP MN-01-GV + CARRY JSON KHÔNG COLLISION + ĐÓNG CÁC NHÓM KHÔNG CÓ BASELINE")
    log("KHÔNG TỰ MERGE JSON KHI CÙNG level_code/form_code XUẤT HIỆN Ở NHIỀU COMPONENT")
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
        fail("DB SHA khác nền Batch 09")

    ro = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True, timeout=60)
    try:
        integ = ro.execute("PRAGMA integrity_check").fetchone()[0]
        fk = ro.execute("PRAGMA foreign_key_check").fetchall()
        log("INTEGRITY_BEFORE =", integ)
        log("FK_BEFORE =", len(fk))
        if integ != "ok" or fk:
            fail("Database health không đạt")

        exmap = execution_map(ro)

        mn_plan = prepare_mn01_plan(ro, exmap)
        network_plan = plan_unique_component_rows(
            ro, "school_network_year_data", "level_code", exmap
        )
        report_plan = plan_unique_component_rows(
            ro, "school_structured_report_inputs", "form_code", exmap
        )

        log("\nMN01_SAFE =", json.dumps(mn_plan["safe"], ensure_ascii=False, default=str))
        log("MN01_DEFERRED =", json.dumps(mn_plan["deferred"], ensure_ascii=False, default=str))

        log("\nNETWORK_SAFE_TARGET_COUNT =", len(network_plan["safe"]))
        log("NETWORK_DEFERRED_TARGET_COUNT =", len(network_plan["deferred"]))
        for x in network_plan["safe"]:
            log(" NETWORK_SAFE =", json.dumps(x, ensure_ascii=False, default=str))
        for x in network_plan["deferred"]:
            log(" NETWORK_DEFERRED =", json.dumps(x, ensure_ascii=False, default=str))

        log("\nREPORT_SAFE_TARGET_COUNT =", len(report_plan["safe"]))
        log("REPORT_DEFERRED_TARGET_COUNT =", len(report_plan["deferred"]))
        for x in report_plan["safe"]:
            log(" REPORT_SAFE =", json.dumps(x, ensure_ascii=False, default=str))
        for x in report_plan["deferred"]:
            log(" REPORT_DEFERRED =", json.dumps(x, ensure_ascii=False, default=str))

        JSON_AUDIT.write_text(
            json.dumps({
                "network": network_plan["audit"],
                "structured_reports": report_plan["audit"],
            }, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8-sig"
        )

        with DEFERRED_CSV.open("w", encoding="utf-8-sig", newline="") as f:
            fields = ["table", "target_id", "school_code", "school_name", "reason", "details"]
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()

            deferred = (
                mn_plan["deferred"]
                + network_plan["deferred"]
                + report_plan["deferred"]
            )
            for x in deferred:
                sid = x.get("target_id")
                s = school(ro, sid) if sid else None
                w.writerow({
                    "table": x.get("table", ""),
                    "target_id": sid or "",
                    "school_code": s[2] if s else "",
                    "school_name": s[3] if s else "",
                    "reason": x.get("reason", ""),
                    "details": json.dumps(x, ensure_ascii=False, default=str),
                })

        nonbaseline_audit_before = audit_nonbaseline_modules(ro)
        log("\nNONBASELINE_AUDIT_BEFORE =", json.dumps(
            nonbaseline_audit_before, ensure_ascii=False, default=str
        ))
    finally:
        ro.close()

    any_write = bool(
        mn_plan["safe"]
        or network_plan["safe"]
        or report_plan["safe"]
    )

    if not any_write:
        log("NO_WRITE = Không có merger target nào đạt gate an toàn.")
        log("BATCH_10_SUCCESS = YES_NO_WRITE")
        if LOG:
            LOG.close()
        return 0

    backup = make_backup()
    log("BACKUP =", backup)
    log("BACKUP_SHA =", sha256_file(backup))

    conn = sqlite3.connect(str(DB), timeout=60)
    conn.execute("PRAGMA foreign_keys=ON")

    try:
        results = {}
        results["school_mn01_gv_inputs"] = execute_mn01(conn, mn_plan)
        results["school_network_year_data"] = clone_component_rows(
            conn, "school_network_year_data", network_plan
        )
        results["school_structured_report_inputs"] = clone_component_rows(
            conn, "school_structured_report_inputs", report_plan
        )

        integ = conn.execute("PRAGMA integrity_check").fetchone()[0]
        fk = conn.execute("PRAGMA foreign_key_check").fetchall()

        remaining = {
            "school_mn01_gv_inputs": final_remaining(
                conn, "school_mn01_gv_inputs"
            ),
            "school_network_year_data": final_remaining(
                conn, "school_network_year_data"
            ),
            "school_structured_report_inputs": final_remaining(
                conn, "school_structured_report_inputs"
            ),
        }

        nonbaseline_audit_after = audit_nonbaseline_modules(conn)

        log("\n" + "=" * 160)
        log("POST VERIFY BATCH 10")
        log("=" * 160)
        log("INTEGRITY_AFTER =", integ)
        log("FK_AFTER =", len(fk))
        log("RESULTS =", json.dumps(results, ensure_ascii=False, default=str))
        log("REMAINING_OFFICIAL_TARGETS =", json.dumps(
            remaining, ensure_ascii=False, default=str
        ))
        log("NONBASELINE_AUDIT_AFTER =", json.dumps(
            nonbaseline_audit_after, ensure_ascii=False, default=str
        ))
        log("DEFERRED_CSV =", DEFERRED_CSV)
        log("JSON_AUDIT =", JSON_AUDIT)
        log("DB_SHA_AFTER =", sha256_file(DB))

        if integ != "ok" or fk:
            fail("Post verify Batch 10 không đạt")

        log("MANUAL_SPLIT_1510_1522_1658 = GIỮ MANUAL, KHÔNG TỰ CHIA.")
        log("FINANCE_CSV_HISTORY_EMPTY_BASELINE = KHÔNG TẠO DỮ LIỆU GIẢ.")
        log("DISABILITY_DETAIL_TABLE_EMPTY = KHÔNG TẠO GIẢ; dữ liệu khuyết tật vẫn kiểm toán qua survey_person_year_records.")
        log("BATCH_10_SUCCESS = YES")
        log(
            "NEXT_STAGE = Batch 11 đọc các collision data_json còn deferred để xác định "
            "form_code/level_code nào có thể tổng hợp theo quy tắc số liệu, rồi xử lý theo lô; "
            "các JSON không có quy tắc cộng rõ ràng tiếp tục giữ manual thay vì ghi đè."
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
            log("BATCH_10_SUCCESS = NO")
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
