# -*- coding: utf-8 -*-
from __future__ import annotations

import csv
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

OUT = EXPORT_DIR / "BATCH_DU_LIEU_HAU_SAP_NHAP_TOAN_TINH_05.txt"
MANUAL_CSV = EXPORT_DIR / "MANUAL_3_NGUON_TACH_DIEM_STAFF.csv"
SURVEY_JSON = EXPORT_DIR / "BATCH_05_AUDIT_NGHIEP_VU_DIEU_TRA.json"

EXPECTED_DB_SHA = "69f6d7a708a8df29700b338c1aea28cc5a7be4e8c3904b83fb2721a986c78fbc"

BASE_YEAR_ID = 1
CURRENT_YEAR_ID = 2
FUTURE_YEAR_ID = 8

MANUAL_SPLIT = {
    1510: {
        "op": "QD3805-OP-0191",
        "source_name": "THCS Nguyễn Văn Trỗi",
        "fixed_target_ids": [1509],
        "extra_target_name_term": "Văn Hiến",
        "note": "Nguồn tách điểm/phần trường; không tự phân nhân sự."
    },
    1522: {
        "op": "QD3805-OP-0132/0133",
        "source_name": "THCS Vạn Phong",
        "fixed_target_ids": [1521, 1523],
        "extra_target_name_term": None,
        "note": "Điểm Diễn Vạn/Diễn Phong về hai đích; không tự phân nhân sự."
    },
    1658: {
        "op": "QD3805-OP-0489",
        "source_name": "THCS Bá - Ngọc",
        "fixed_target_ids": [1660, 1657],
        "extra_target_name_term": None,
        "note": "Nguồn giải thể/tách hai điểm; không tự phân nhân sự."
    },
}

SURVEY_KEYWORDS = (
    "survey", "household", "person", "investig", "assignment", "progress",
    "batch", "area", "reconciliation", "disability", "lock", "handover",
    "teacher_assignment", "enumerator"
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

def table_names(conn):
    return [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()]

def table_info(conn, table):
    return conn.execute(f"PRAGMA table_info({qi(table)})").fetchall()

def cols(conn, table):
    return [r[1] for r in table_info(conn, table)]

def fk_info(conn, table):
    return conn.execute(f"PRAGMA foreign_key_list({qi(table)})").fetchall()

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
    if "id" not in cols(conn, table):
        return None
    max_id = int(conn.execute(
        f"SELECT COALESCE(MAX(id),0) FROM {qi(table)}"
    ).fetchone()[0])
    h = rows_hash(conn.execute(
        f"SELECT * FROM {qi(table)} WHERE id<=? ORDER BY id", (max_id,)
    ))
    return max_id, h

def old_rows_unchanged(conn, table, baseline):
    if baseline is None:
        return True
    max_id, old_hash = baseline
    h = rows_hash(conn.execute(
        f"SELECT * FROM {qi(table)} WHERE id<=? ORDER BY id", (max_id,)
    ))
    return h == old_hash

def make_backup():
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = BACKUP_DIR / f"backup_truoc_BATCH_DU_LIEU_05_{ts}.db"

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

def school(conn, sid):
    return conn.execute(
        "SELECT id,commune_id,code,name,is_active FROM schools WHERE id=?",
        (sid,)
    ).fetchone()

def active_school_ids(conn):
    return [int(r[0]) for r in conn.execute(
        "SELECT id FROM schools WHERE is_active=1 ORDER BY id"
    ).fetchall()]

def summary_rows(conn, sid, year_id):
    cur = conn.execute(
        "SELECT * FROM school_staff_year_summaries "
        "WHERE school_id=? AND school_year_id=? ORDER BY id",
        (sid, year_id)
    )
    names = [d[0] for d in cur.description]
    return [dict(zip(names, r)) for r in cur.fetchall()]

def official_execs_for_target(conn, sid):
    rows = conn.execute(
        "SELECT id,plan_id,operation_id,target_school_id,source_school_ids_json,summary_json "
        "FROM school_merger_official_executions "
        "WHERE school_year_id=? AND target_school_id=? ORDER BY id",
        (CURRENT_YEAR_ID, sid)
    ).fetchall()
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
            "id": r[0],
            "plan_id": r[1],
            "operation_id": r[2],
            "target_school_id": int(r[3]),
            "source_ids": src,
            "summary": summary,
        })
    return out

def remaining_summary_targets(conn):
    out = []
    for sid in active_school_ids(conn):
        y1 = len(summary_rows(conn, sid, BASE_YEAR_ID))
        y2 = len(summary_rows(conn, sid, CURRENT_YEAR_ID))
        staff2 = conn.execute(
            "SELECT COUNT(*) FROM staff_year_records WHERE school_id=? AND school_year_id=?",
            (sid, CURRENT_YEAR_ID)
        ).fetchone()[0]
        if staff2 > 0 and y1 > 0 and y2 == 0:
            out.append(sid)
    return out

def prepare_summary_aggregation(conn):
    candidates = remaining_summary_targets(conn)
    safe = []
    skipped = []

    for sid in candidates:
        execs = official_execs_for_target(conn, sid)
        if len(execs) != 1:
            skipped.append((sid, "OFFICIAL_EXEC_COUNT_NOT_1", len(execs), school(conn, sid)))
            continue

        ex = execs[0]
        target_rows = summary_rows(conn, sid, BASE_YEAR_ID)
        if len(target_rows) != 1:
            skipped.append((sid, "TARGET_BASE_SUMMARY_NOT_1", len(target_rows), school(conn, sid)))
            continue

        component_ids = [sid] + ex["source_ids"]
        component_rows = []
        missing = []
        for cid in component_ids:
            rows = summary_rows(conn, cid, BASE_YEAR_ID)
            if len(rows) != 1:
                missing.append((cid, len(rows), school(conn, cid)))
            else:
                component_rows.append((cid, rows[0]))

        if missing:
            skipped.append((sid, "COMPONENT_BASE_SUMMARY_MISSING", missing, school(conn, sid)))
            continue

        groups = {str(row["institution_group"]) for _, row in component_rows}
        if len(groups) != 1:
            skipped.append((sid, "INSTITUTION_GROUP_MISMATCH", sorted(groups), school(conn, sid)))
            continue

        totals = {
            "total_groups_classes": sum(int(row.get("total_groups_classes") or 0) for _, row in component_rows),
            "preschool_classes_3_4": sum(int(row.get("preschool_classes_3_4") or 0) for _, row in component_rows),
            "preschool_classes_5": sum(int(row.get("preschool_classes_5") or 0) for _, row in component_rows),
        }

        safe.append({
            "target_id": sid,
            "school": school(conn, sid),
            "execution": ex,
            "component_ids": component_ids,
            "institution_group": next(iter(groups)),
            "totals": totals,
        })

    return candidates, safe, skipped

def tx_aggregate_remaining_summaries(conn):
    log("\n" + "="*160)
    log("TRANSACTION A - TỔNG HỢP 5 SUMMARY CÒN LẠI THEO OFFICIAL MERGER")
    log("="*160)

    if not table_exists(conn, "school_staff_year_summaries"):
        log("SUMMARY_AGG_TRANSACTION = SKIP_TABLE_NOT_FOUND")
        return {"status": "SKIP", "inserted": 0}

    candidates, safe, skipped = prepare_summary_aggregation(conn)
    log("SUMMARY_REMAINING_CANDIDATES =", candidates)
    log("SUMMARY_SAFE_AGGREGATION_COUNT =", len(safe))
    log("SUMMARY_SKIPPED_COUNT =", len(skipped))

    for x in safe:
        log(" SUMMARY_SAFE =", json.dumps(x, ensure_ascii=False, default=str))
    for x in skipped:
        log(" SUMMARY_SKIPPED =", x)

    if not safe:
        log("SUMMARY_AGG_TRANSACTION = SKIP_NO_SAFE_TARGETS")
        return {"status": "SKIP", "inserted": 0, "skipped": skipped}

    baseline = old_rows_baseline(conn, "school_staff_year_summaries")
    before_other = {
        "staff_year_records": conn.execute("SELECT COUNT(*) FROM staff_year_records").fetchone()[0],
        "schools": conn.execute("SELECT COUNT(*) FROM schools").fetchone()[0],
        "users": conn.execute("SELECT COUNT(*) FROM users").fetchone()[0],
    }

    conn.execute("BEGIN IMMEDIATE")
    try:
        created = 0
        for x in safe:
            sid = x["target_id"]
            if summary_rows(conn, sid, CURRENT_YEAR_ID):
                fail(f"Target {sid} đã có summary y2")

            conn.execute(
                """
                INSERT INTO school_staff_year_summaries
                (school_id,school_year_id,institution_group,total_groups_classes,
                 preschool_classes_3_4,preschool_classes_5,notes,updated_by_user_id,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?)
                """,
                (
                    sid,
                    CURRENT_YEAR_ID,
                    x["institution_group"],
                    x["totals"]["total_groups_classes"],
                    x["totals"]["preschool_classes_3_4"],
                    x["totals"]["preschool_classes_5"],
                    "Tổng hợp tự động 2026-2027 từ summary 2025-2026 của trường đích và các trường nguồn theo phương án sáp nhập chính thức.",
                    None,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f"),
                )
            )
            created += 1

        if created != len(safe):
            fail(f"Summary created {created} != safe {len(safe)}")

        if not old_rows_unchanged(conn, "school_staff_year_summaries", baseline):
            fail("Summary cũ bị thay đổi")

        after_other = {
            "staff_year_records": conn.execute("SELECT COUNT(*) FROM staff_year_records").fetchone()[0],
            "schools": conn.execute("SELECT COUNT(*) FROM schools").fetchone()[0],
            "users": conn.execute("SELECT COUNT(*) FROM users").fetchone()[0],
        }
        if after_other != before_other:
            fail(f"Bảng ngoài summary bị thay đổi count: {before_other} -> {after_other}")

        for x in safe:
            rows = summary_rows(conn, x["target_id"], CURRENT_YEAR_ID)
            if len(rows) != 1:
                fail(f"Target {x['target_id']} summary y2 != 1")

        fk = conn.execute("PRAGMA foreign_key_check").fetchall()
        if fk:
            fail(f"FK lỗi summary aggregation: {fk[:20]}")

        conn.commit()
        log("SUMMARY_AGG_TRANSACTION = COMMIT")
        log("SUMMARY_AGG_INSERTED =", created)
        return {"status": "COMMIT", "inserted": created, "skipped": skipped}

    except Exception:
        conn.rollback()
        log("SUMMARY_AGG_TRANSACTION = ROLLBACK")
        raise

def staff_member_brief(conn, member_id):
    if not table_exists(conn, "staff_members"):
        return (member_id, None, None)
    return conn.execute(
        "SELECT id,code,full_name FROM staff_members WHERE id=?",
        (member_id,)
    ).fetchone()

def target_options(conn, cfg):
    opts = []
    for sid in cfg["fixed_target_ids"]:
        s = school(conn, sid)
        if s:
            opts.append(s)

    term = cfg.get("extra_target_name_term")
    if term:
        rows = conn.execute(
            "SELECT id,commune_id,code,name,is_active FROM schools "
            "WHERE name LIKE ? AND is_active=1 ORDER BY commune_id,id",
            (f"%{term}%",)
        ).fetchall()
        for r in rows:
            if r not in opts:
                opts.append(r)
    return opts

def export_manual_split_pack(conn):
    log("\n" + "="*160)
    log("B - XUẤT GÓI 3 NGUỒN TÁCH ĐIỂM ĐỂ CẬP NHẬT NGHIỆP VỤ")
    log("KHÔNG GHI DB")
    log("="*160)

    fields = [
        "operation",
        "source_school_id",
        "source_school_code",
        "source_school_name",
        "destination_options",
        "staff_member_id",
        "staff_code",
        "full_name",
        "position_group",
        "position_title",
        "teaching_subject",
        "status_code",
        "source_status_label",
        "target_school_id_to_fill",
        "note",
    ]

    rows_out = []
    for sid, cfg in MANUAL_SPLIT.items():
        s = school(conn, sid)
        options = target_options(conn, cfg)
        option_text = " | ".join(
            f"{x[0]}:{x[2]}:{x[3]}" for x in options
        )
        staff_rows = conn.execute(
            """
            SELECT staff_member_id,position_group,position_title,teaching_subject,
                   status_code,source_status_label,is_active
            FROM staff_year_records
            WHERE school_id=? AND school_year_id=?
            ORDER BY position_group,staff_member_id
            """,
            (sid, BASE_YEAR_ID)
        ).fetchall()

        log("MANUAL_SOURCE =", s)
        log("DESTINATION_OPTIONS =", options)
        log("STAFF_Y1_COUNT =", len(staff_rows))

        for r in staff_rows:
            member_id = int(r[0])
            m = staff_member_brief(conn, member_id)
            rows_out.append({
                "operation": cfg["op"],
                "source_school_id": sid,
                "source_school_code": s[2] if s else "",
                "source_school_name": s[3] if s else cfg["source_name"],
                "destination_options": option_text,
                "staff_member_id": member_id,
                "staff_code": m[1] if m else "",
                "full_name": m[2] if m else "",
                "position_group": r[1],
                "position_title": r[2],
                "teaching_subject": r[3],
                "status_code": r[4],
                "source_status_label": r[5],
                "target_school_id_to_fill": "",
                "note": cfg["note"],
            })

    with MANUAL_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows_out)

    log("MANUAL_SPLIT_CSV =", MANUAL_CSV)
    log("MANUAL_SPLIT_CSV_ROWS =", len(rows_out))
    log("POLICY = Không tự điền target_school_id. Chỉ chuyển người khi có danh sách thực tế được xác nhận.")
    return len(rows_out)

def status_counts(conn, table, status_col):
    try:
        return conn.execute(
            f"SELECT {qi(status_col)},COUNT(*) FROM {qi(table)} "
            f"GROUP BY {qi(status_col)} ORDER BY COUNT(*) DESC,{qi(status_col)}"
        ).fetchall()
    except sqlite3.Error:
        return []

def year_counts(conn, table, year_col):
    try:
        return conn.execute(
            f"SELECT {qi(year_col)},COUNT(*) FROM {qi(table)} "
            f"GROUP BY {qi(year_col)} ORDER BY {qi(year_col)}"
        ).fetchall()
    except sqlite3.Error:
        return []

def survey_domain_audit(conn):
    log("\n" + "="*160)
    log("C - KIỂM TOÁN TOÀN BỘ NGHIỆP VỤ ĐIỀU TRA / HỘ DÂN / PHÂN CÔNG / KHÓA")
    log("CHỈ ĐỌC")
    log("="*160)

    audit = {}
    domain_tables = [
        t for t in table_names(conn)
        if any(k in t.lower() for k in SURVEY_KEYWORDS)
    ]

    log("SURVEY_DOMAIN_TABLE_COUNT =", len(domain_tables))
    log("SURVEY_DOMAIN_TABLES =", domain_tables)

    for t in domain_tables:
        c = cols(conn, t)
        count = conn.execute(f"SELECT COUNT(*) FROM {qi(t)}").fetchone()[0]
        item = {
            "count": count,
            "columns": c,
            "foreign_keys": fk_info(conn, t),
        }

        if "school_year_id" in c:
            item["year_counts"] = year_counts(conn, t, "school_year_id")
        elif "year_id" in c:
            item["year_counts"] = year_counts(conn, t, "year_id")

        for sc in ("status", "state", "lock_status", "is_locked", "is_active", "completed_status"):
            if sc in c:
                item[f"{sc}_counts"] = status_counts(conn, t, sc)

        audit[t] = item

        log("\nTABLE =", t)
        log(" COUNT =", count)
        log(" COLUMNS =", c)
        log(" FOREIGN_KEYS =", item["foreign_keys"])
        if "year_counts" in item:
            log(" YEAR_COUNTS =", item["year_counts"])
        for k, v in item.items():
            if k.endswith("_counts") and k != "year_counts":
                log(" ", k.upper(), "=", v)

    # Survey batch detail, no PII.
    if table_exists(conn, "survey_batches"):
        c = cols(conn, "survey_batches")
        select_cols = [x for x in (
            "id", "school_year_id", "commune_id", "code", "name", "status",
            "is_locked", "is_active", "opened_at", "locked_at"
        ) if x in c]
        if select_cols:
            rows = conn.execute(
                f"SELECT {', '.join(qi(x) for x in select_cols)} "
                f"FROM survey_batches "
                + ("WHERE school_year_id=? " if "school_year_id" in c else "")
                + "ORDER BY id LIMIT 300",
                ((CURRENT_YEAR_ID,) if "school_year_id" in c else ())
            ).fetchall()
            log("\nSURVEY_BATCH_CURRENT_ROWS_COLUMNS =", select_cols)
            log("SURVEY_BATCH_CURRENT_ROWS =", rows)

    # Tìm các bảng trực tiếp tham chiếu household/person/batch/assignment để chuẩn bị Batch 06.
    dependency = {}
    for t in table_names(conn):
        fks = fk_info(conn, t)
        refs = [
            x for x in fks
            if any(k in str(x[2]).lower() for k in ("survey", "household", "person", "assignment", "batch"))
        ]
        if refs:
            dependency[t] = refs

    log("\nSURVEY_DEPENDENCY_TABLES =", json.dumps(dependency, ensure_ascii=False, default=str))

    # Chỉ ghi metadata audit ra JSON, không ghi bản ghi cá nhân.
    SURVEY_JSON.write_text(
        json.dumps(audit, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8-sig"
    )
    log("SURVEY_AUDIT_JSON =", SURVEY_JSON)
    return audit

def final_audit(conn):
    log("\n" + "="*160)
    log("D - KIỂM TOÁN KẾT THÚC BATCH 05")
    log("="*160)

    missing_staff = []
    for sid in active_school_ids(conn):
        y1 = conn.execute(
            "SELECT COUNT(*) FROM staff_year_records WHERE school_id=? AND school_year_id=?",
            (sid, BASE_YEAR_ID)
        ).fetchone()[0]
        y2 = conn.execute(
            "SELECT COUNT(*) FROM staff_year_records WHERE school_id=? AND school_year_id=?",
            (sid, CURRENT_YEAR_ID)
        ).fetchone()[0]
        if y1 > 0 and y2 == 0:
            missing_staff.append((sid, y1, school(conn, sid)))

    remaining_summary = remaining_summary_targets(conn)

    log("REMAINING_STAFF_Y2_ZERO =", missing_staff)
    log("REMAINING_SUMMARY_WITH_BASELINE_Y2_ZERO =", remaining_summary)

    # Trường source split vẫn cố ý để trống y2 cho tới khi có bảng phân bổ thực tế.
    remaining_staff_ids = {int(x[0]) for x in missing_staff}
    manual_ids = set(MANUAL_SPLIT)
    log("REMAINING_STAFF_EXACTLY_MANUAL_SPLIT_SET =", "YES" if remaining_staff_ids == manual_ids else "NO")

    return missing_staff, remaining_summary

def main():
    global LOG
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    LOG = OUT.open("w", encoding="utf-8-sig", newline="\n")

    log("="*160)
    log("BATCH DỮ LIỆU HẬU SÁP NHẬP TOÀN TỈNH 05")
    log("TỔNG HỢP SUMMARY MERGER TARGET + ĐÓNG 3 NGUỒN TÁCH ĐIỂM THEO GÓI MANUAL + AUDIT ĐIỀU TRA/HỘ DÂN")
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
        fail("DB SHA khác nền Batch 04")

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

    try:
        summary_result = tx_aggregate_remaining_summaries(conn)
        manual_rows = export_manual_split_pack(conn)
        survey_audit = survey_domain_audit(conn)
        missing_staff, remaining_summary = final_audit(conn)

        integ = conn.execute("PRAGMA integrity_check").fetchone()[0]
        fk = conn.execute("PRAGMA foreign_key_check").fetchall()

        log("\n" + "="*160)
        log("POST VERIFY BATCH 05")
        log("="*160)
        log("INTEGRITY_AFTER =", integ)
        log("FK_AFTER =", len(fk))
        log("SUMMARY_RESULT =", json.dumps({
            "status": summary_result.get("status"),
            "inserted": summary_result.get("inserted", 0),
            "skipped_count": len(summary_result.get("skipped", [])),
        }, ensure_ascii=False))
        log("MANUAL_SPLIT_CSV_ROWS =", manual_rows)
        log("SURVEY_DOMAIN_TABLES_AUDITED =", len(survey_audit))
        log("DB_SHA_AFTER =", sha256_file(DB))

        if integ != "ok" or fk:
            fail("Post verify Batch 05 không đạt")

        log("BATCH_05_SUCCESS = YES")
        log("DATABASE_BACKUP =", backup)
        log("MANUAL_SPLIT_POLICY = 3 nguồn còn lại không tự chuyển nhân sự. File CSV đã xuất để cập nhật khi có danh sách phân bổ thực tế.")
        log("NEXT_STAGE = Batch 06 sẽ dùng chính schema điều tra/hộ dân/phân công/khóa vừa audit để xử lý đồng loạt các nghiệp vụ điều tra mà không quay lại từng trường.")
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
            log("BATCH_05_SUCCESS = NO")
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
