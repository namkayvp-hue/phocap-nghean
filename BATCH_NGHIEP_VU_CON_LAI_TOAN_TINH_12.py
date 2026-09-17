# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import inspect
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
OUT = EXPORT_DIR / "BATCH_NGHIEP_VU_CON_LAI_TOAN_TINH_12.txt"

# Nền ngay sau Batch 11.
EXPECTED_DB_SHA = "80a35bdab22c48fa896aa16286ed834b9280bbcc601afa148c10f0c728d516b6"

BASE_YEAR_ID = 1
CURRENT_YEAR_ID = 2
FUTURE_YEAR_ID = 8

MANUAL_SPLIT_SOURCE_IDS = {1510, 1522, 1658}

# Các chỉ tiêu mạng lưới MN là số lượng cộng được giữa các đơn vị thành phần.
MN_SUM_KEYS = {
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

CORE_FIELDS = {
    "TH_01_GV": {"principal", "vice_principal", "teacher_total"},
    "THCS_01_GV": {"principal", "vice_principal", "teacher_total"},
}

DANGEROUS_SOURCE_TOKENS = (
    ".commit(",
    ".rollback(",
    ".add(",
    ".delete(",
    ".flush(",
    "insert(",
    "update(",
    "delete(",
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


def make_backup():
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = BACKUP_DIR / f"backup_truoc_BATCH_NGHIEP_VU_12_{ts}.db"

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


def is_number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def merge_mn_network(payloads):
    if not payloads:
        return None, ["NO_PAYLOADS"]
    if not all(isinstance(p, dict) for p in payloads):
        return None, ["PAYLOAD_NOT_DICT"]

    keysets = [set(p) for p in payloads]
    if any(k != keysets[0] for k in keysets[1:]):
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

        if key in MN_SUM_KEYS:
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

        # Các thuộc tính không có quy tắc cộng chỉ được giữ khi giống hệt.
        if all(v == vals[0] for v in vals):
            merged[key] = vals[0]
        else:
            reasons.append(f"{key}:UNSAFE_CONFLICT={vals}")

    if reasons:
        return None, reasons
    return merged, []


def prepare_mn_network(conn):
    exmap = official_exec_map(conn)
    safe = []
    deferred = []

    targets = [
        int(r[0]) for r in conn.execute(
            """
            SELECT DISTINCT n.school_id
            FROM school_network_year_data n
            WHERE n.school_year_id=?
              AND UPPER(COALESCE(n.level_code,''))='MN'
              AND n.school_id IN (
                    SELECT target_school_id
                    FROM school_merger_official_executions
                    WHERE school_year_id=?
              )
            ORDER BY n.school_id
            """,
            (BASE_YEAR_ID, CURRENT_YEAR_ID)
        ).fetchall()
        if count_sy(conn, "school_network_year_data", int(r[0]), CURRENT_YEAR_ID) == 0
    ]

    for tid in targets:
        execs = exmap.get(tid, [])
        if len(execs) != 1:
            deferred.append((tid, "OFFICIAL_EXEC_COUNT", len(execs)))
            continue

        ex = execs[0]
        component_ids = [tid] + ex["source_ids"]

        rows = []
        payloads = []
        bad = None

        for cid in component_ids:
            rr = [
                x for x in dict_rows(conn, "school_network_year_data", cid, BASE_YEAR_ID)
                if str(x.get("level_code") or "").upper() == "MN"
            ]
            if len(rr) != 1:
                bad = ("COMPONENT_MN_ROW_NOT_1", cid, len(rr))
                break
            try:
                payload = json.loads(rr[0]["data_json"])
            except Exception as exc:
                bad = ("JSON_PARSE_ERROR", cid, repr(exc))
                break
            rows.append((cid, rr[0]))
            payloads.append(payload)

        if bad:
            deferred.append((tid, bad, component_ids))
            continue

        merged, reasons = merge_mn_network(payloads)
        if reasons:
            deferred.append((tid, "MERGE_GATE", reasons, component_ids))
            continue

        safe.append({
            "target_id": tid,
            "school": school(conn, tid),
            "component_ids": component_ids,
            "execution": ex,
            "merged_json": merged,
        })

    return safe, deferred


def execute_mn_network(conn, item):
    tid = int(item["target_id"])

    conn.execute("BEGIN IMMEDIATE")
    try:
        if count_sy(conn, "school_network_year_data", tid, CURRENT_YEAR_ID) != 0:
            fail(f"MN network target {tid} vừa có y2")

        for cid in item["component_ids"]:
            if count_sy(conn, "school_network_year_data", cid, BASE_YEAR_ID) <= 0:
                fail(f"MN network component {cid} mất baseline")

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
                json.dumps(item["merged_json"], ensure_ascii=False, separators=(",", ":")),
                "Batch 12 - tổng hợp mạng lưới MN theo official merger",
                now,
            )
        )

        rr = dict_rows(conn, "school_network_year_data", tid, CURRENT_YEAR_ID)
        if len(rr) != 1:
            fail(f"MN target {tid}: y2 row count={len(rr)}")
        if json.loads(rr[0]["data_json"]) != item["merged_json"]:
            fail(f"MN target {tid}: JSON post mismatch")

        fk = conn.execute("PRAGMA foreign_key_check").fetchall()
        if fk:
            fail(f"MN target {tid}: FK={fk[:20]}")

        conn.commit()
        return "COMMIT"
    except Exception:
        conn.rollback()
        raise


def assert_readonly_helper(func, name):
    src = inspect.getsource(func)
    low = src.lower()
    if any(tok in low for tok in DANGEROUS_SOURCE_TOKENS):
        fail(f"Helper {name} có dấu hiệu ghi dữ liệu")
    return hashlib.sha256(src.encode("utf-8")).hexdigest()


def catalog_by_form_code():
    from app.structured_report_catalog import STRUCTURED_SCHOOL_FORMS

    out = {}
    for slug, cfg in STRUCTURED_SCHOOL_FORMS.items():
        code = str(cfg.get("form_code") or "")
        if code:
            out[code] = cfg
    return out


def form_field_codes(cfg):
    result = set()
    for group in cfg.get("groups") or []:
        for field in group.get("fields") or []:
            code = field.get("code")
            if code:
                result.add(str(code))
    return result


def prepare_structured_staff_rows(sqlite_conn):
    from sqlalchemy.orm import Session
    from app.database import engine
    import app.pcgd_xmc_report_builders_v1 as builders

    required = {
        "_staff_rows": builders._staff_rows,
        "_staff_summary": builders._staff_summary,
        "_schools_and_classes": builders._schools_and_classes,
        "_class_count_with_network": builders._class_count_with_network,
    }

    helper_hashes = {}
    for name, func in required.items():
        helper_hashes[name] = assert_readonly_helper(func, name)

    log("REPORT_HELPER_HASHES =", json.dumps(helper_hashes, ensure_ascii=False))

    catalog = catalog_by_form_code()
    for code in ("TH_01_GV", "THCS_01_GV"):
        if code not in catalog:
            fail(f"Không tìm thấy catalog {code}")

    exmap = official_exec_map(sqlite_conn)

    candidates = []
    # Mỗi target có baseline TH/THCS structured staff form.
    for r in sqlite_conn.execute(
        """
        SELECT DISTINCT school_id,form_code
        FROM school_structured_report_inputs
        WHERE school_year_id=?
          AND UPPER(COALESCE(form_code,'')) IN ('TH_01_GV','THCS_01_GV')
          AND school_id IN (
                SELECT target_school_id
                FROM school_merger_official_executions
                WHERE school_year_id=?
          )
        ORDER BY school_id,form_code
        """,
        (BASE_YEAR_ID, CURRENT_YEAR_ID)
    ).fetchall():
        candidates.append((int(r[0]), str(r[1]).upper()))

    safe = []
    deferred = []

    with Session(engine) as db:
        for tid, form_code in candidates:
            if tid in MANUAL_SPLIT_SOURCE_IDS:
                deferred.append((tid, form_code, "MANUAL_SPLIT_SOURCE"))
                continue

            if len(exmap.get(tid, [])) != 1:
                deferred.append((tid, form_code, "OFFICIAL_EXEC_COUNT"))
                continue

            level = "TH" if form_code == "TH_01_GV" else "THCS"

            try:
                schools, grades = builders._schools_and_classes(
                    db,
                    CURRENT_YEAR_ID,
                    None,
                    tid,
                )
            except Exception as exc:
                deferred.append((tid, form_code, "SCHOOLS_CLASSES_ERROR", repr(exc)))
                continue

            target_present = any(int(s.id) == tid for s in schools)
            if not target_present:
                deferred.append((tid, form_code, "TARGET_NOT_IN_SOURCE_SCOPE"))
                continue

            try:
                records_map = builders._staff_rows(
                    db,
                    CURRENT_YEAR_ID,
                    [tid],
                )
                staff_rows = records_map.get(tid, [])
                class_count = builders._class_count_with_network(
                    db,
                    school_id=tid,
                    school_year_id=CURRENT_YEAR_ID,
                    grades=grades,
                    level=level,
                )
                summary = builders._staff_summary(staff_rows, class_count)
            except Exception as exc:
                deferred.append((tid, form_code, "HELPER_ERROR", repr(exc)))
                continue

            if not isinstance(summary, dict):
                deferred.append((tid, form_code, "SUMMARY_NOT_DICT", type(summary).__name__))
                continue

            field_codes = form_field_codes(catalog[form_code])
            generated = {
                key: summary[key]
                for key in sorted(field_codes)
                if key in summary
            }

            missing_core = sorted(CORE_FIELDS[form_code] - set(generated))
            if missing_core:
                deferred.append((
                    tid, form_code, "MISSING_CORE_FIELDS",
                    missing_core, sorted(summary.keys())
                ))
                continue

            # Ít nhất phải có nhân sự hiện hành.
            direct_staff_count = int(sqlite_conn.execute(
                """
                SELECT COUNT(*)
                FROM staff_year_records
                WHERE school_id=? AND school_year_id=? AND is_active=1
                """,
                (tid, CURRENT_YEAR_ID)
            ).fetchone()[0])
            if direct_staff_count <= 0:
                deferred.append((tid, form_code, "NO_ACTIVE_Y2_STAFF"))
                continue

            existing_y2 = dict_rows(
                sqlite_conn,
                "school_structured_report_inputs",
                tid,
                CURRENT_YEAR_ID,
                form_code=form_code,
            )

            action = "INSERT"
            existing_row_id = None
            preserve_existing = {}

            if len(existing_y2) == 1:
                current = existing_y2[0]

                # Chỉ cho UPDATE nếu y2 là bản auto-carry y1 rõ ràng:
                # không có người cập nhật và data_json giống hệt baseline target.
                baseline = dict_rows(
                    sqlite_conn,
                    "school_structured_report_inputs",
                    tid,
                    BASE_YEAR_ID,
                    form_code=form_code,
                )

                if (
                    len(baseline) == 1
                    and current.get("updated_by_user_id") is None
                    and str(current.get("data_json") or "") == str(baseline[0].get("data_json") or "")
                ):
                    action = "UPDATE_AUTO_CARRY"
                    existing_row_id = int(current["id"])
                    try:
                        preserve_existing = json.loads(current.get("data_json") or "{}")
                        if not isinstance(preserve_existing, dict):
                            preserve_existing = {}
                    except Exception:
                        preserve_existing = {}
                else:
                    deferred.append((
                        tid, form_code, "EXISTING_Y2_NOT_SAFE_TO_OVERWRITE",
                        current.get("id"), current.get("updated_by_user_id")
                    ))
                    continue

            elif len(existing_y2) > 1:
                deferred.append((tid, form_code, "MULTIPLE_EXISTING_Y2", len(existing_y2)))
                continue

            merged_data = dict(preserve_existing)
            merged_data.update(generated)

            safe.append({
                "target_id": tid,
                "school": school(sqlite_conn, tid),
                "form_code": form_code,
                "level": level,
                "action": action,
                "existing_row_id": existing_row_id,
                "active_staff_count": direct_staff_count,
                "helper_staff_rows": len(staff_rows),
                "class_count": class_count,
                "generated": generated,
                "merged_data": merged_data,
            })

    return safe, deferred, helper_hashes


def execute_structured_target(conn, item):
    tid = int(item["target_id"])
    form_code = item["form_code"]
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")

    conn.execute("BEGIN IMMEDIATE")
    try:
        existing = dict_rows(
            conn,
            "school_structured_report_inputs",
            tid,
            CURRENT_YEAR_ID,
            form_code=form_code,
        )

        if item["action"] == "INSERT":
            if existing:
                fail(f"{tid}/{form_code}: y2 appeared before INSERT")

            conn.execute(
                """
                INSERT INTO school_structured_report_inputs
                (school_id,school_year_id,form_code,data_json,notes,updated_by_user_id,updated_at)
                VALUES (?,?,?,?,?,?,?)
                """,
                (
                    tid,
                    CURRENT_YEAR_ID,
                    form_code,
                    json.dumps(item["merged_data"], ensure_ascii=False, separators=(",", ":")),
                    "Batch 12 - tự động tái sinh các chỉ tiêu đội ngũ từ staff_year_records 2026-2027 bằng helper báo cáo hiện hành; không tự điền trường định tính không có nguồn.",
                    None,
                    now,
                )
            )

        elif item["action"] == "UPDATE_AUTO_CARRY":
            if len(existing) != 1 or int(existing[0]["id"]) != int(item["existing_row_id"]):
                fail(f"{tid}/{form_code}: existing row changed")

            cur = conn.execute(
                """
                UPDATE school_structured_report_inputs
                SET data_json=?,
                    notes=?,
                    updated_by_user_id=NULL,
                    updated_at=?
                WHERE id=? AND updated_by_user_id IS NULL
                """,
                (
                    json.dumps(item["merged_data"], ensure_ascii=False, separators=(",", ":")),
                    "Batch 12 - làm mới bản auto-carry bằng staff_year_records 2026-2027 theo helper báo cáo hiện hành; giữ nguyên các trường cũ không bị helper ghi đè.",
                    now,
                    int(item["existing_row_id"]),
                )
            )
            if cur.rowcount != 1:
                fail(f"{tid}/{form_code}: UPDATE rowcount={cur.rowcount}")
        else:
            fail(f"Unknown action {item['action']}")

        post = dict_rows(
            conn,
            "school_structured_report_inputs",
            tid,
            CURRENT_YEAR_ID,
            form_code=form_code,
        )
        if len(post) != 1:
            fail(f"{tid}/{form_code}: post row count={len(post)}")

        actual_json = json.loads(post[0]["data_json"])
        for key, expected in item["generated"].items():
            if actual_json.get(key) != expected:
                fail(f"{tid}/{form_code}: key mismatch {key}")

        fk = conn.execute("PRAGMA foreign_key_check").fetchall()
        if fk:
            fail(f"{tid}/{form_code}: FK errors {fk[:20]}")

        conn.commit()
        return "COMMIT"

    except Exception:
        conn.rollback()
        raise


def remaining_network(conn):
    exmap = official_exec_map(conn)
    out = []
    for tid in sorted(exmap):
        if (
            count_sy(conn, "school_network_year_data", tid, BASE_YEAR_ID) > 0
            and count_sy(conn, "school_network_year_data", tid, CURRENT_YEAR_ID) == 0
        ):
            out.append((tid, school(conn, tid), exmap[tid][0]["source_ids"] if len(exmap[tid]) == 1 else []))
    return out


def remaining_structured(conn):
    exmap = official_exec_map(conn)
    out = []
    for tid in sorted(exmap):
        base = conn.execute(
            """
            SELECT form_code,COUNT(*)
            FROM school_structured_report_inputs
            WHERE school_id=? AND school_year_id=?
              AND UPPER(COALESCE(form_code,'')) IN ('TH_01_GV','THCS_01_GV')
            GROUP BY form_code
            """,
            (tid, BASE_YEAR_ID)
        ).fetchall()
        for form_code, cnt in base:
            y2 = conn.execute(
                """
                SELECT COUNT(*)
                FROM school_structured_report_inputs
                WHERE school_id=? AND school_year_id=? AND form_code=?
                """,
                (tid, CURRENT_YEAR_ID, form_code)
            ).fetchone()[0]
            if int(cnt) > 0 and int(y2) == 0:
                out.append((tid, form_code, school(conn, tid)))
    return out


def main():
    global LOG
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    LOG = OUT.open("w", encoding="utf-8-sig", newline="\n")

    log("=" * 160)
    log("BATCH NGHIỆP VỤ CÒN LẠI TOÀN TỈNH 12")
    log("MẠNG LƯỚI MN: TỔNG HỢP CHỈ TIÊU SỐ LƯỢNG + STRUCTURED TH/THCS: TÁI SINH TỪ HELPER BÁO CÁO HIỆN HÀNH")
    log("KHÔNG CỘNG MÙ JSON; KHÔNG GHI ĐÈ DÒNG Y2 DO NGƯỜI DÙNG CẬP NHẬT")
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
        fail("DB SHA khác nền Batch 11")

    ro = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True, timeout=60)
    try:
        integ = ro.execute("PRAGMA integrity_check").fetchone()[0]
        fk = ro.execute("PRAGMA foreign_key_check").fetchall()
        log("INTEGRITY_BEFORE =", integ)
        log("FK_BEFORE =", len(fk))
        if integ != "ok" or fk:
            fail("Database health không đạt")

        mn_safe, mn_deferred = prepare_mn_network(ro)
        log("MN_NETWORK_SAFE_COUNT =", len(mn_safe))
        log("MN_NETWORK_DEFERRED_COUNT =", len(mn_deferred))
        for x in mn_safe:
            log(" MN_SAFE =", json.dumps(x, ensure_ascii=False, default=str))
        for x in mn_deferred:
            log(" MN_DEFERRED =", x)

        structured_safe, structured_deferred, helper_hashes = prepare_structured_staff_rows(ro)
        log("STRUCTURED_SAFE_COUNT =", len(structured_safe))
        log("STRUCTURED_DEFERRED_COUNT =", len(structured_deferred))
        for x in structured_safe:
            # Không in toàn bộ dữ liệu nhạy cảm; chỉ metadata + generated counts.
            log(" STRUCTURED_SAFE =", json.dumps({
                "target_id": x["target_id"],
                "school": x["school"],
                "form_code": x["form_code"],
                "action": x["action"],
                "active_staff_count": x["active_staff_count"],
                "helper_staff_rows": x["helper_staff_rows"],
                "class_count": x["class_count"],
                "generated_keys": sorted(x["generated"]),
                "teacher_total": x["generated"].get("teacher_total"),
                "principal": x["generated"].get("principal"),
                "vice_principal": x["generated"].get("vice_principal"),
            }, ensure_ascii=False, default=str))
        for x in structured_deferred:
            log(" STRUCTURED_DEFERRED =", x)

    finally:
        ro.close()

    if not mn_safe and not structured_safe:
        log("NO_WRITE = Không có target nào đạt gate.")
        log("DB_SHA_AFTER =", sha256_file(DB))
        log("BATCH_12_SUCCESS = YES_NO_WRITE")
        if LOG:
            LOG.close()
        return 0

    backup = make_backup()
    log("BACKUP =", backup)
    log("BACKUP_SHA =", sha256_file(backup))

    conn = sqlite3.connect(str(DB), timeout=60)
    conn.execute("PRAGMA foreign_keys=ON")

    mn_results = []
    structured_results = []

    try:
        for item in mn_safe:
            tid = item["target_id"]
            try:
                status = execute_mn_network(conn, item)
                mn_results.append((tid, status, None))
                log("MN_NETWORK_TARGET", tid, "=", status)
            except Exception as exc:
                mn_results.append((tid, "ROLLBACK", repr(exc)))
                log("MN_NETWORK_TARGET", tid, "= ROLLBACK", repr(exc))

        for item in structured_safe:
            tid = item["target_id"]
            code = item["form_code"]
            try:
                status = execute_structured_target(conn, item)
                structured_results.append((tid, code, item["action"], status, None))
                log("STRUCTURED_TARGET", tid, code, item["action"], "=", status)
            except Exception as exc:
                structured_results.append((tid, code, item["action"], "ROLLBACK", repr(exc)))
                log("STRUCTURED_TARGET", tid, code, "= ROLLBACK", repr(exc))

        integ = conn.execute("PRAGMA integrity_check").fetchone()[0]
        fk = conn.execute("PRAGMA foreign_key_check").fetchall()

        rem_network = remaining_network(conn)
        rem_structured = remaining_structured(conn)

        log("\n" + "=" * 160)
        log("POST VERIFY BATCH 12")
        log("=" * 160)
        log("INTEGRITY_AFTER =", integ)
        log("FK_AFTER =", len(fk))
        log("MN_RESULTS =", mn_results)
        log("STRUCTURED_RESULTS =", structured_results)
        log("REMAINING_NETWORK_COUNT =", len(rem_network))
        for x in rem_network:
            log(" REMAINING_NETWORK =", x)
        log("REMAINING_STRUCTURED_STAFF_COUNT =", len(rem_structured))
        for x in rem_structured:
            log(" REMAINING_STRUCTURED =", x)
        log("DB_SHA_AFTER =", sha256_file(DB))

        if integ != "ok" or fk:
            fail("Post verify Batch 12 không đạt")

        log("POLICY_NETWORK_NULL_MIX = VẪN DEFER, KHÔNG COI NULL=0.")
        log("POLICY_STRUCTURED = Chỉ sinh các field có trong source helper + catalog; trường định tính không có nguồn vẫn giữ trống/cũ.")
        log("MANUAL_SPLIT_1510_1522_1658 = GIỮ MANUAL.")
        log("BATCH_12_SUCCESS = YES")
        log(
            "NEXT_STAGE = Batch 13 đóng nốt network deferred theo nhóm có dữ liệu thiếu/NULL, "
            "không tự suy diễn; đồng thời kiểm toán cuối các phân hệ đối chiếu, khuyết tật, "
            "CSVC-TBDH, tài chính, tiêu chuẩn và 3 nguồn tách điểm để xác định phần nào cần nhập thực tế."
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
            log("BATCH_12_SUCCESS = NO")
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
