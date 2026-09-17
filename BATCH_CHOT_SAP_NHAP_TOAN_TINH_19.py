# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from collections import Counter
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

OUT = EXPORT_DIR / "BATCH_CHOT_SAP_NHAP_TOAN_TINH_19.txt"
JSON_OUT = EXPORT_DIR / "BATCH_19_CHOT_SAP_NHAP.json"

EXPECTED_DB_SHA = "2a43e36ff8f192abb46668faa1366ed7242984bfd876f90572cd83b90ee7837e"

CURRENT_YEAR_ID = 2
BASE_YEAR_ID = 1
FUTURE_YEAR_ID = 8

MANUAL_SPLIT_SOURCE_IDS = {1510, 1522, 1658}

NETWORK_ROUTER = ROOT / "app" / "routers" / "network_current.py"
MENU_FILE = ROOT / "app" / "templates" / "partials" / "dropdown_menu_v1.html"

LOG = None


def log(*args):
    s = " ".join(str(x) for x in args)
    print(s)
    if LOG:
        LOG.write(s + "\n")
        LOG.flush()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone() is not None


def columns(conn: sqlite3.Connection, table: str) -> set[str]:
    if not table_exists(conn, table):
        return set()
    return {str(r[1]) for r in conn.execute(f'PRAGMA table_info("{table}")').fetchall()}


def official_rows(conn: sqlite3.Connection):
    return conn.execute(
        """
        SELECT id,plan_id,operation_id,target_school_id,source_school_ids_json
        FROM school_merger_official_executions
        WHERE school_year_id=?
        ORDER BY id
        """,
        (CURRENT_YEAR_ID,),
    ).fetchall()


def parse_sources(value) -> list[int]:
    try:
        raw = json.loads(value or "[]")
    except Exception:
        return []
    result = []
    for x in raw:
        try:
            sid = int(x)
        except Exception:
            continue
        if sid not in result:
            result.append(sid)
    return result


def make_final_backup() -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = BACKUP_DIR / f"backup_CHOT_SAU_SAP_NHAP_{ts}.db"

    src = sqlite3.connect(str(DB), timeout=60)
    dst = sqlite3.connect(str(path), timeout=60)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()

    chk = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=30)
    try:
        integrity = chk.execute("PRAGMA integrity_check").fetchone()[0]
        fk = chk.execute("PRAGMA foreign_key_check").fetchall()
    finally:
        chk.close()

    if integrity != "ok" or fk:
        raise RuntimeError(
            f"Backup chốt không đạt: integrity={integrity}, fk={len(fk)}"
        )
    return path


def current_residual_count(conn: sqlite3.Connection, table: str, source_ids: list[int]) -> int | None:
    if not source_ids or not table_exists(conn, table):
        return 0

    c = columns(conn, table)
    if "school_id" not in c or "school_year_id" not in c:
        return None

    placeholders = ",".join("?" for _ in source_ids)
    row = conn.execute(
        f"""
        SELECT COUNT(*)
        FROM "{table}"
        WHERE school_year_id=?
          AND school_id IN ({placeholders})
        """,
        (CURRENT_YEAR_ID, *source_ids),
    ).fetchone()
    return int(row[0])


def future_footprint_count(conn: sqlite3.Connection, table: str, school_ids: list[int]) -> int | None:
    if not school_ids or not table_exists(conn, table):
        return 0
    c = columns(conn, table)
    if "school_id" not in c or "school_year_id" not in c:
        return None

    placeholders = ",".join("?" for _ in school_ids)
    return int(conn.execute(
        f"""
        SELECT COUNT(*)
        FROM "{table}"
        WHERE school_year_id=?
          AND school_id IN ({placeholders})
        """,
        (FUTURE_YEAR_ID, *school_ids),
    ).fetchone()[0])


def active_source_logins(conn: sqlite3.Connection, source_ids: list[int]):
    if not source_ids or not table_exists(conn, "users"):
        return []

    c = columns(conn, "users")
    if "school_id" not in c:
        return []

    placeholders = ",".join("?" for _ in source_ids)
    select_cols = ["id", "username", "school_id"]
    if "is_active" in c:
        select_cols.append("is_active")

    sql = (
        "SELECT " + ",".join(select_cols)
        + f" FROM users WHERE school_id IN ({placeholders})"
    )
    if "is_active" in c:
        sql += " AND is_active=1"

    cur = conn.execute(sql, tuple(source_ids))
    names = [d[0] for d in cur.description]
    return [dict(zip(names, r)) for r in cur.fetchall()]


def active_source_schools(conn: sqlite3.Connection, source_ids: list[int]):
    if not source_ids:
        return []
    placeholders = ",".join("?" for _ in source_ids)
    cur = conn.execute(
        f"""
        SELECT id,code,name,commune_id,is_active
        FROM schools
        WHERE id IN ({placeholders})
          AND is_active=1
        ORDER BY id
        """,
        tuple(source_ids),
    )
    names = [d[0] for d in cur.description]
    return [dict(zip(names, r)) for r in cur.fetchall()]


def cbql_audit(conn: sqlite3.Connection, target_ids: list[int]):
    if not target_ids:
        return {"generic_cbql": 0, "residual_ht_pht": []}

    placeholders = ",".join("?" for _ in target_ids)

    generic = int(conn.execute(
        f"""
        SELECT COUNT(*)
        FROM staff_year_records
        WHERE school_year_id=?
          AND school_id IN ({placeholders})
          AND UPPER(TRIM(COALESCE(position_group,'')))='CBQL'
          AND UPPER(TRIM(COALESCE(position_title,'')))='CBQL'
        """,
        (CURRENT_YEAR_ID, *target_ids),
    ).fetchone()[0])

    rows = conn.execute(
        f"""
        SELECT id,staff_member_id,school_id,position_group,position_title
        FROM staff_year_records
        WHERE school_year_id=?
          AND school_id IN ({placeholders})
        """,
        (CURRENT_YEAR_ID, *target_ids),
    ).fetchall()

    residual = []
    for r in rows:
        title = str(r[4] or "").lower()
        norm = (
            title.replace("ệ", "e")
                 .replace("ư", "u")
                 .replace("ở", "o")
                 .replace("ó", "o")
                 .replace("ố", "o")
                 .replace("ồ", "o")
                 .replace("ờ", "o")
                 .replace("ấ", "a")
                 .replace("ầ", "a")
                 .replace("ã", "a")
                 .replace("đ", "d")
        )
        if "hieu truong" in norm or "hiệu trưởng" in title:
            residual.append({
                "staff_year_record_id": r[0],
                "staff_member_id": r[1],
                "school_id": r[2],
                "position_group": r[3],
                "position_title": r[4],
            })

    return {
        "generic_cbql": generic,
        "residual_ht_pht": residual,
    }


def network_pending(conn: sqlite3.Connection, official_target_ids: list[int]):
    pending = []
    for tid in official_target_ids:
        # Chỉ xem là pending nếu có dữ liệu mạng lưới nền tại target hoặc source,
        # nhưng chưa có bất kỳ dòng năm 2026-2027 tại target.
        y2 = int(conn.execute(
            """
            SELECT COUNT(*)
            FROM school_network_year_data
            WHERE school_id=? AND school_year_id=?
            """,
            (tid, CURRENT_YEAR_ID),
        ).fetchone()[0])
        if y2 > 0:
            continue

        source_json_rows = conn.execute(
            """
            SELECT source_school_ids_json
            FROM school_merger_official_executions
            WHERE school_year_id=? AND target_school_id=?
            """,
            (CURRENT_YEAR_ID, tid),
        ).fetchall()
        source_ids = []
        for row in source_json_rows:
            for sid in parse_sources(row[0]):
                if sid not in source_ids:
                    source_ids.append(sid)

        component_ids = [tid] + source_ids
        placeholders = ",".join("?" for _ in component_ids)
        y1 = int(conn.execute(
            f"""
            SELECT COUNT(*)
            FROM school_network_year_data
            WHERE school_year_id=?
              AND school_id IN ({placeholders})
            """,
            (BASE_YEAR_ID, *component_ids),
        ).fetchone()[0])

        if y1 <= 0:
            continue

        s = conn.execute(
            "SELECT id,code,name,commune_id FROM schools WHERE id=?",
            (tid,),
        ).fetchone()

        pending.append({
            "target_id": tid,
            "code": s[1] if s else "",
            "name": s[2] if s else "",
            "commune_id": s[3] if s else None,
            "source_ids": source_ids,
            "status": "OPERATIONAL_DATA_PENDING_NOT_MERGER_BLOCKER",
        })

    return pending


def manual_split_audit(conn: sqlite3.Connection):
    rows = []
    for sid in sorted(MANUAL_SPLIT_SOURCE_IDS):
        s = conn.execute(
            "SELECT id,code,name,commune_id,is_active FROM schools WHERE id=?",
            (sid,),
        ).fetchone()
        staff_y1 = int(conn.execute(
            """
            SELECT COUNT(*)
            FROM staff_year_records
            WHERE school_id=? AND school_year_id=?
            """,
            (sid, BASE_YEAR_ID),
        ).fetchone()[0])
        staff_y2 = int(conn.execute(
            """
            SELECT COUNT(*)
            FROM staff_year_records
            WHERE school_id=? AND school_year_id=?
            """,
            (sid, CURRENT_YEAR_ID),
        ).fetchone()[0])

        rows.append({
            "school_id": sid,
            "code": s[1] if s else "",
            "name": s[2] if s else "",
            "commune_id": s[3] if s else None,
            "is_active": s[4] if s else None,
            "staff_y1": staff_y1,
            "staff_y2": staff_y2,
            "status": "MANUAL_PENDING",
        })
    return rows


def ui_audit():
    result = {
        "router_exists": NETWORK_ROUTER.exists(),
        "menu_exists": MENU_FILE.exists(),
        "router_has_get": False,
        "router_has_post": False,
        "menu_has_link": False,
    }

    if NETWORK_ROUTER.exists():
        text = NETWORK_ROUTER.read_text(encoding="utf-8", errors="ignore")
        result["router_has_get"] = '@router.get("")' in text
        result["router_has_post"] = '@router.post("/luu")' in text

    if MENU_FILE.exists():
        text = MENU_FILE.read_text(encoding="utf-8", errors="ignore")
        result["menu_has_link"] = "/mang-luoi-hien-hanh" in text

    return result


def main():
    global LOG

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    LOG = OUT.open("w", encoding="utf-8-sig", newline="\n")

    log("=" * 160)
    log("BATCH 19 - CHỐT SÁP NHẬP TOÀN TỈNH")
    log("KIỂM TOÁN CUỐI + TẠO BACKUP MỐC SAU SÁP NHẬP")
    log("KHÔNG GHI DATABASE")
    log("=" * 160)

    sha = sha256_file(DB)
    log("DB_SHA =", sha)
    log("EXPECTED_DB_SHA =", EXPECTED_DB_SHA)
    if sha != EXPECTED_DB_SHA:
        raise RuntimeError("DB SHA khác nền đã khóa sau Batch 18C.")

    conn = sqlite3.connect(
        f"file:{DB.as_posix()}?mode=ro",
        uri=True,
        timeout=60,
    )
    conn.row_factory = sqlite3.Row

    try:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        fk = conn.execute("PRAGMA foreign_key_check").fetchall()
        log("INTEGRITY =", integrity)
        log("FK =", len(fk))
        if integrity != "ok" or fk:
            raise RuntimeError("Database health không đạt.")

        rows = official_rows(conn)
        if not rows:
            raise RuntimeError("Không có school_merger_official_executions năm 2026-2027.")

        plan_ids = [str(r["plan_id"] or "") for r in rows]
        operation_ids = [str(r["operation_id"] or "") for r in rows]
        duplicate_plans = sorted([x for x, n in Counter(plan_ids).items() if x and n > 1])
        duplicate_ops = sorted([x for x, n in Counter(operation_ids).items() if x and n > 1])

        target_ids = sorted({int(r["target_school_id"]) for r in rows if r["target_school_id"] is not None})
        source_ids = []
        for r in rows:
            for sid in parse_sources(r["source_school_ids_json"]):
                if sid not in source_ids:
                    source_ids.append(sid)
        source_ids = sorted(source_ids)

        log("OFFICIAL_EXECUTION_COUNT =", len(rows))
        log("OFFICIAL_TARGET_COUNT =", len(target_ids))
        log("OFFICIAL_SOURCE_COUNT =", len(source_ids))
        log("DUPLICATE_PLAN_IDS =", duplicate_plans)
        log("DUPLICATE_OPERATION_IDS =", duplicate_ops)

        if duplicate_plans or duplicate_ops:
            raise RuntimeError("Có trùng plan_id hoặc operation_id trong official executions.")

        manual_intersection = sorted(set(source_ids) & MANUAL_SPLIT_SOURCE_IDS)
        log("MANUAL_SPLIT_INTERSECTION_WITH_OFFICIAL_SOURCES =", manual_intersection)
        if manual_intersection:
            raise RuntimeError(
                "Ba nguồn tách điểm manual không được nằm trong official full-merger source."
            )

        active_sources = active_source_schools(conn, source_ids)
        source_logins = active_source_logins(conn, source_ids)
        log("ACTIVE_OFFICIAL_SOURCE_SCHOOLS =", len(active_sources))
        log("ACTIVE_SOURCE_LOGINS =", len(source_logins))

        if active_sources:
            log(" ACTIVE_SOURCE_DETAIL =", json.dumps(active_sources, ensure_ascii=False))
        if source_logins:
            log(" ACTIVE_SOURCE_LOGIN_DETAIL =", json.dumps(source_logins, ensure_ascii=False))

        if active_sources:
            raise RuntimeError("Vẫn còn official source school đang active.")
        if source_logins:
            raise RuntimeError("Vẫn còn tài khoản active tại official source school.")

        blocking_tables = [
            "staff_year_records",
            "classes",
            "student_enrollments",
        ]
        residuals = {}
        for table in blocking_tables:
            residuals[table] = current_residual_count(conn, table, source_ids)
        log("CURRENT_SOURCE_BLOCKING_RESIDUALS =", json.dumps(residuals, ensure_ascii=False))

        if any((v or 0) != 0 for v in residuals.values()):
            raise RuntimeError("Còn dữ liệu lõi năm 2026-2027 tại official source.")

        nonblocking_tables = [
            "school_network_year_data",
            "school_structured_report_inputs",
            "school_mn01_gv_inputs",
            "school_staff_year_summaries",
        ]
        nonblocking_residuals = {}
        for table in nonblocking_tables:
            nonblocking_residuals[table] = current_residual_count(conn, table, source_ids)
        log("CURRENT_SOURCE_NONBLOCKING_RESIDUALS =", json.dumps(nonblocking_residuals, ensure_ascii=False))

        future_tables = [
            "staff_year_records",
            "classes",
            "student_enrollments",
            "school_network_year_data",
            "school_structured_report_inputs",
        ]
        future = {}
        all_merger_ids = sorted(set(target_ids) | set(source_ids))
        for table in future_tables:
            future[table] = future_footprint_count(conn, table, all_merger_ids)
        log("FUTURE_YEAR8_FOOTPRINTS =", json.dumps(future, ensure_ascii=False))

        if any((v or 0) != 0 for v in future.values()):
            raise RuntimeError("Có footprint FUTURE year_id=8 trên vùng sáp nhập.")

        cbql = cbql_audit(conn, target_ids)
        log("GENERIC_CBQL_AT_TARGETS =", cbql["generic_cbql"])
        log("RESIDUAL_HT_PHT_TITLE_COUNT =", len(cbql["residual_ht_pht"]))
        if cbql["residual_ht_pht"]:
            log(" RESIDUAL_HT_PHT =", json.dumps(cbql["residual_ht_pht"], ensure_ascii=False))
            raise RuntimeError("Vẫn còn title HT/PHT cũ tại official target.")

        pending_network = network_pending(conn, target_ids)
        log("NETWORK_OPERATIONAL_PENDING_COUNT =", len(pending_network))
        for item in pending_network:
            log(" NETWORK_PENDING =", json.dumps(item, ensure_ascii=False))

        manual_split = manual_split_audit(conn)
        log("MANUAL_SPLIT_CASES =", json.dumps(manual_split, ensure_ascii=False))

        ui = ui_audit()
        log("NETWORK_UI_AUDIT =", json.dumps(ui, ensure_ascii=False))
        if not all([
            ui["router_exists"],
            ui["menu_exists"],
            ui["router_has_get"],
            ui["router_has_post"],
            ui["menu_has_link"],
        ]):
            raise RuntimeError("Màn hình/menu mạng lưới hiện hành chưa đủ để bàn giao.")

    finally:
        conn.close()

    backup = make_final_backup()
    backup_sha = sha256_file(backup)

    summary = {
        "db_sha": sha,
        "integrity": "ok",
        "fk": 0,
        "official_execution_count": len(rows),
        "official_target_count": len(target_ids),
        "official_source_count": len(source_ids),
        "active_official_source_schools": 0,
        "active_source_logins": 0,
        "blocking_source_residuals": residuals,
        "nonblocking_source_residuals": nonblocking_residuals,
        "future_year8_footprints": future,
        "generic_cbql_at_targets": cbql["generic_cbql"],
        "residual_ht_pht_titles": 0,
        "network_operational_pending_count": len(pending_network),
        "network_operational_pending": pending_network,
        "manual_split_cases": manual_split,
        "network_ui": ui,
        "final_backup": str(backup),
        "final_backup_sha": backup_sha,
        "merger_closed": True,
        "merger_close_note": (
            "Sáp nhập chính thức đã đóng. Network còn thiếu là dữ liệu vận hành hiện hành, "
            "không phải tồn đọng engine sáp nhập. Ba nguồn tách điểm tiếp tục MANUAL_PENDING."
        ),
        "next_stage": "KIEM_THU_DIEU_TRA_HO_DAN",
    }

    JSON_OUT.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8-sig",
    )

    log("\n" + "=" * 160)
    log("KẾT LUẬN BATCH 19")
    log("=" * 160)
    log("FINAL_BACKUP =", backup)
    log("FINAL_BACKUP_SHA =", backup_sha)
    log("DB_SHA_AFTER_READ_ONLY =", sha256_file(DB))
    log("DATABASE_WRITES_THIS_RUN = 0")
    log("SCHOOL_MERGER_OFFICIALLY_CLOSED = YES")
    log("NETWORK_PENDING_IS_OPERATIONAL_DATA_NOT_MERGER_BLOCKER = YES")
    log("MANUAL_SPLIT_1510_1522_1658 = MANUAL_PENDING")
    log("NEXT_STAGE = KIỂM THỬ NGHIỆP VỤ ĐIỀU TRA HỘ DÂN")
    log("BATCH_19_SUCCESS = YES")
    log("=" * 160)

    if LOG:
        LOG.close()
    return 0


if __name__ == "__main__":
    try:
        rc = main()
    except Exception as exc:
        try:
            log("\n" + "=" * 160)
            log("BATCH_19_SUCCESS = NO")
            log("ERROR =", repr(exc))
            if DB.exists():
                log("DB_SHA_CURRENT =", sha256_file(DB))
            log("SCHOOL_MERGER_OFFICIALLY_CLOSED = NO")
            log("DỪNG AN TOÀN.")
            log("=" * 160)
        finally:
            if LOG and not LOG.closed:
                LOG.close()
        rc = 1

    sys.exit(rc)
