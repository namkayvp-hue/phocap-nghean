# -*- coding: utf-8 -*-
from __future__ import annotations

import csv
import hashlib
import sqlite3
import sys
import unicodedata
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

OUT = EXPORT_DIR / "BATCH_CHUAN_HOA_CBQL_SAU_SAP_NHAP_14B.txt"
CSV_AUDIT = EXPORT_DIR / "BATCH_14B_CBQL_DA_CHUAN_HOA.csv"

# Nền ngay sau Batch 13.
EXPECTED_DB_SHA = "e88895bfe7b39bf65a886b836354ead82632e947266feeabd05412d97f239c5e"
CURRENT_YEAR_ID = 2

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


def norm_text(value):
    s = str(value or "").strip().lower()
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = s.replace("đ", "d")
    return " ".join(s.split())


def is_principal_or_vice(title):
    t = norm_text(title)
    if not t:
        return False

    # Các dạng tên chức vụ phổ biến đang có trong dữ liệu.
    exact_or_contains = (
        "hieu truong",
        "pho hieu truong",
        "phó hiệu trưởng",
        "principal",
        "vice principal",
    )
    if any(norm_text(x) in t for x in exact_or_contains):
        return True

    # Viết tắt độc lập.
    tokens = set(t.replace("-", " ").split())
    if "ht" in tokens or "pht" in tokens:
        return True

    return False


def make_backup():
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = BACKUP_DIR / f"backup_truoc_CHUAN_HOA_CBQL_14B_{ts}.db"

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


def main():
    global LOG

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    LOG = OUT.open("w", encoding="utf-8-sig", newline="\n")

    log("=" * 150)
    log("BATCH 14B - CHUẨN HÓA HIỆU TRƯỞNG/PHÓ HIỆU TRƯỞNG SAU SÁP NHẬP → CBQL")
    log("CHỈ ÁP DỤNG NĂM 2026-2027 TẠI CÁC OFFICIAL MERGER TARGET")
    log("LỊCH SỬ NĂM CŨ GIỮ NGUYÊN; TỪNG TRƯỜNG SẼ TỰ SỬA CHỨC VỤ THỰC TẾ SAU")
    log("=" * 150)

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
        fail("DB SHA khác nền sau Batch 13")

    ro = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True, timeout=60)

    try:
        integ = ro.execute("PRAGMA integrity_check").fetchone()[0]
        fk = ro.execute("PRAGMA foreign_key_check").fetchall()

        log("INTEGRITY_BEFORE =", integ)
        log("FK_BEFORE =", len(fk))

        if integ != "ok" or fk:
            fail("Database health không đạt")

        target_ids = {
            int(r[0])
            for r in ro.execute(
                """
                SELECT DISTINCT target_school_id
                FROM school_merger_official_executions
                WHERE school_year_id=?
                  AND target_school_id IS NOT NULL
                """,
                (CURRENT_YEAR_ID,)
            ).fetchall()
        }

        log("OFFICIAL_TARGET_COUNT =", len(target_ids))

        cur = ro.execute(
            """
            SELECT
                y.id,
                y.staff_member_id,
                y.school_id,
                s.code AS school_code,
                s.name AS school_name,
                m.code AS staff_code,
                m.full_name,
                y.position_group,
                y.position_title,
                y.status_code,
                y.source_status_label
            FROM staff_year_records y
            JOIN schools s ON s.id=y.school_id
            LEFT JOIN staff_members m ON m.id=y.staff_member_id
            WHERE y.school_year_id=?
              AND y.school_id IN (
                    SELECT DISTINCT target_school_id
                    FROM school_merger_official_executions
                    WHERE school_year_id=?
              )
            ORDER BY y.school_id,y.id
            """,
            (CURRENT_YEAR_ID, CURRENT_YEAR_ID)
        )

        names = [d[0] for d in cur.description]
        candidates = []

        for row in cur.fetchall():
            d = dict(zip(names, row))
            if is_principal_or_vice(d.get("position_title")):
                candidates.append(d)

        log("CANDIDATE_ROWS =", len(candidates))

        by_school = {}
        for d in candidates:
            by_school.setdefault(d["school_id"], 0)
            by_school[d["school_id"]] += 1

        log("CANDIDATE_SCHOOL_COUNT =", len(by_school))
        for sid, n in sorted(by_school.items()):
            school_name = next(
                (x["school_name"] for x in candidates if x["school_id"] == sid),
                ""
            )
            log(" TARGET =", sid, school_name, "ROWS =", n)

    finally:
        ro.close()

    if not candidates:
        log("NO_WRITE = Không có Hiệu trưởng/Phó hiệu trưởng cần chuẩn hóa.")
        log("BATCH_14B_SUCCESS = YES_NO_WRITE")
        return 0

    backup = make_backup()
    log("BACKUP =", backup)
    log("BACKUP_SHA =", sha256_file(backup))

    conn = sqlite3.connect(str(DB), timeout=60)
    conn.execute("PRAGMA foreign_keys=ON")

    try:
        conn.execute("BEGIN IMMEDIATE")

        updated = 0

        for d in candidates:
            current = conn.execute(
                """
                SELECT position_group,position_title,school_year_id,school_id
                FROM staff_year_records
                WHERE id=?
                """,
                (d["id"],)
            ).fetchone()

            if not current:
                fail(f"staff_year_record id={d['id']} biến mất")

            if int(current[2]) != CURRENT_YEAR_ID:
                fail(f"id={d['id']} không còn thuộc năm 2026-2027")

            if int(current[3]) != int(d["school_id"]):
                fail(f"id={d['id']} đổi school_id trước transaction")

            if not is_principal_or_vice(current[1]):
                fail(f"id={d['id']} position_title đã thay đổi trước transaction")

            cur = conn.execute(
                """
                UPDATE staff_year_records
                SET position_group='CBQL',
                    position_title='CBQL'
                WHERE id=?
                  AND school_year_id=?
                """,
                (d["id"], CURRENT_YEAR_ID)
            )

            if cur.rowcount != 1:
                fail(f"UPDATE id={d['id']} rowcount={cur.rowcount}")

            updated += 1

        if updated != len(candidates):
            fail(f"updated={updated} candidates={len(candidates)}")

        # Không được còn HT/PHT tại các official target năm 2026-2027.
        check_rows = conn.execute(
            """
            SELECT y.id,y.position_title
            FROM staff_year_records y
            WHERE y.school_year_id=?
              AND y.school_id IN (
                    SELECT DISTINCT target_school_id
                    FROM school_merger_official_executions
                    WHERE school_year_id=?
              )
            """,
            (CURRENT_YEAR_ID, CURRENT_YEAR_ID)
        ).fetchall()

        residual = [
            (rid, title)
            for rid, title in check_rows
            if is_principal_or_vice(title)
        ]

        if residual:
            fail(f"Còn residual HT/PHT sau chuẩn hóa: {residual[:20]}")

        fk = conn.execute("PRAGMA foreign_key_check").fetchall()
        if fk:
            fail(f"FK lỗi trước COMMIT: {fk[:20]}")

        conn.commit()
        log("TRANSACTION_COMMIT = PASS")
        log("UPDATED_ROWS =", updated)

    except Exception:
        conn.rollback()
        log("TRANSACTION_ROLLBACK = PASS")
        raise

    finally:
        conn.close()

    # Xuất danh sách để từng trường biết ai cần cập nhật chức vụ thật.
    with CSV_AUDIT.open("w", encoding="utf-8-sig", newline="") as f:
        fields = [
            "school_id", "school_code", "school_name",
            "staff_member_id", "staff_code", "full_name",
            "old_position_group", "old_position_title",
            "new_position_group", "new_position_title",
            "action_for_school"
        ]
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()

        for d in candidates:
            w.writerow({
                "school_id": d["school_id"],
                "school_code": d["school_code"],
                "school_name": d["school_name"],
                "staff_member_id": d["staff_member_id"],
                "staff_code": d["staff_code"],
                "full_name": d["full_name"],
                "old_position_group": d["position_group"],
                "old_position_title": d["position_title"],
                "new_position_group": "CBQL",
                "new_position_title": "CBQL",
                "action_for_school": "Trường tự cập nhật lại chức vụ Hiệu trưởng/Phó hiệu trưởng theo thực tế 2026-2027",
            })

    # Post verify.
    ro = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True, timeout=60)
    try:
        integ = ro.execute("PRAGMA integrity_check").fetchone()[0]
        fk = ro.execute("PRAGMA foreign_key_check").fetchall()

        changed = ro.execute(
            """
            SELECT COUNT(*)
            FROM staff_year_records
            WHERE school_year_id=?
              AND school_id IN (
                    SELECT DISTINCT target_school_id
                    FROM school_merger_official_executions
                    WHERE school_year_id=?
              )
              AND position_group='CBQL'
              AND position_title='CBQL'
            """,
            (CURRENT_YEAR_ID, CURRENT_YEAR_ID)
        ).fetchone()[0]

        log("\n" + "=" * 150)
        log("POST VERIFY BATCH 14B")
        log("=" * 150)
        log("INTEGRITY_AFTER =", integ)
        log("FK_AFTER =", len(fk))
        log("CBQL_GENERIC_ROWS_AT_OFFICIAL_TARGETS =", changed)
        log("AUDIT_CSV =", CSV_AUDIT)
        log("DB_SHA_AFTER =", sha256_file(DB))

        if integ != "ok" or fk:
            fail("Post verify không đạt")

        log("POLICY = HT/PHT tại official merger target năm 2026-2027 đã đưa chung thành CBQL.")
        log("HISTORY = Các năm cũ không thay đổi.")
        log("SCHOOL_ACTION = Từng trường tự sửa lại chức vụ thực tế sau.")
        log("BATCH_14B_SUCCESS = YES")
        log("NEXT_STAGE = Rà nghiệp vụ hiện hành; không còn coi nhiều Hiệu trưởng/Phó hiệu trưởng sau sáp nhập là lỗi dữ liệu.")
        log("=" * 150)

    finally:
        ro.close()
        if LOG:
            LOG.close()

    return 0


if __name__ == "__main__":
    try:
        code = main()
    except Exception as exc:
        try:
            log("\n" + "=" * 150)
            log("BATCH_14B_SUCCESS = NO")
            log("ERROR =", repr(exc))
            if DB.exists():
                log("DB_SHA_CURRENT =", sha256_file(DB))
            log("DỪNG AN TOÀN.")
            log("=" * 150)
        finally:
            if LOG and not LOG.closed:
                LOG.close()
        code = 1

    sys.exit(code)
