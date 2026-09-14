# -*- coding: utf-8 -*-
"""
PREVIEW THCS MẬU ĐÔN -> PTDT BÁN TRÚ THCS THẠCH NGÀN
QĐ3805-OP-0108
CHỈ ĐỌC - KHÔNG GHI DATABASE

Nguồn khóa:
- id=1578
- code=40422510
- Trường THCS Mậu Đôn

Đích khóa:
- id=1577
- code=40422504
- PTDT Bán trú THCS Thạch Ngàn

Mục tiêu:
- Kiểm tra đúng nguồn/đích.
- Kiểm tra dấu vết thực hiện trước.
- Mô phỏng gộp toàn trường cho dữ liệu hiện hành 2026-2027,
  trong đó dữ liệu nhân sự nền lấy từ 2025-2026.
- Không INSERT/UPDATE/DELETE.
- Kiểm tra SHA trước/sau.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from pathlib import Path
from collections import Counter, defaultdict

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

SOURCE_ID = 1578
SOURCE_CODE = "40422510"
SOURCE_NAME = "Trường THCS Mậu Đôn"

TARGET_ID = 1577
TARGET_CODE = "40422504"
TARGET_NAME = "PTDT Bán trú THCS Thạch Ngàn"

COMMUNE_ID = 64
OFFICIAL_OPERATION_ID = "QD3805-OP-0108"

PAST_YEAR_ID = 1      # 2025-2026
CURRENT_YEAR_ID = 2   # 2026-2027

EXCLUDED_STATUS_CODES = {
    "NGHI_HUU",
    "CHUYEN_DI",
    "THOI_VIEC",
    "DA_NGHI",
}
EXCLUDED_SOURCE_LABELS = {
    "Đã nghỉ hưu",
    "Đã chuyển đi",
    "Nghỉ hưu",
    "Chuyển đi",
}

def qi(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            b = f.read(1024 * 1024)
            if not b:
                break
            h.update(b)
    return h.hexdigest()

def find_db() -> Path:
    root = Path(__file__).resolve().parent
    candidates = [
        root / "data" / "phocap.db",
        root / "phocap.db",
        Path(r"C:\PhoCap\data\phocap.db"),
        Path(r"C:\PhoCap\phocap.db"),
    ]
    for p in candidates:
        if p.exists():
            return p
    print("DỪNG AN TOÀN: không tìm thấy phocap.db")
    sys.exit(2)

def get_tables(conn):
    return [r[0] for r in conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type='table' AND name NOT LIKE 'sqlite_%'
        ORDER BY name
        """
    ).fetchall()]

def get_columns(conn, table):
    return conn.execute(f"PRAGMA table_info({qi(table)})").fetchall()

def column_names(conn, table):
    return [r[1] for r in get_columns(conn, table)]

def print_json(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))

def school_row(conn, school_id):
    cur = conn.execute("SELECT * FROM schools WHERE id=?", (school_id,))
    row = cur.fetchone()
    if row is None:
        return None
    return {cur.description[i][0]: row[i] for i in range(len(row))}

def lock_school(conn, school_id, code, expected_name_contains, commune_id):
    row = school_row(conn, school_id)
    if not row:
        raise RuntimeError(f"Không tìm thấy school_id={school_id}")
    if str(row.get("code")) != str(code):
        raise RuntimeError(f"school_id={school_id} sai code: {row.get('code')} != {code}")
    if expected_name_contains.lower() not in str(row.get("name", "")).lower():
        raise RuntimeError(f"school_id={school_id} sai tên: {row.get('name')}")
    if int(row.get("commune_id")) != int(commune_id):
        raise RuntimeError(f"school_id={school_id} sai commune_id: {row.get('commune_id')}")
    return row

def count_by_year_for_school(conn, table, school_id):
    cols = column_names(conn, table)
    if "school_id" not in cols:
        return []
    if "school_year_id" in cols:
        return conn.execute(
            f"""
            SELECT school_year_id, COUNT(*)
            FROM {qi(table)}
            WHERE school_id=?
            GROUP BY school_year_id
            ORDER BY school_year_id
            """,
            (school_id,)
        ).fetchall()
    total = conn.execute(
        f"SELECT COUNT(*) FROM {qi(table)} WHERE school_id=?",
        (school_id,)
    ).fetchone()[0]
    return [(None, total)]

def footprint(conn, school_id):
    result = []
    for table in get_tables(conn):
        cols = column_names(conn, table)
        if "school_id" not in cols:
            continue
        try:
            groups = count_by_year_for_school(conn, table, school_id)
        except sqlite3.Error:
            continue
        total = sum(c for _, c in groups)
        if total:
            result.append({
                "table": table,
                "total": total,
                "by_year": groups,
            })
    return result

def staff_rows(conn, school_id, year_id):
    cols = column_names(conn, "staff_year_records")
    needed = [
        "id", "staff_member_id", "school_year_id", "school_id",
        "status_code", "position_group", "position_title",
        "is_active", "source_status_label"
    ]
    selected = [c for c in needed if c in cols]
    cur = conn.execute(
        f"""
        SELECT {", ".join(qi(c) for c in selected)}
        FROM staff_year_records
        WHERE school_id=? AND school_year_id=?
        ORDER BY staff_member_id, id
        """,
        (school_id, year_id)
    )
    names = [d[0] for d in cur.description]
    return [dict(zip(names, r)) for r in cur.fetchall()]

def staff_is_eligible(row):
    status = str(row.get("status_code") or "").strip().upper()
    label = str(row.get("source_status_label") or "").strip()
    active = row.get("is_active")
    if active is not None and int(active) != 1:
        return False, "is_active != 1"
    if status in EXCLUDED_STATUS_CODES:
        return False, f"status_code={status}"
    if label in EXCLUDED_SOURCE_LABELS:
        return False, f"source_status_label={label}"
    return True, ""

def summarize_staff(rows):
    out = {
        "TOTAL": len(rows),
        "ELIGIBLE": 0,
        "EXCLUDED": 0,
        "POSITION_GROUP": Counter(),
        "STATUS_CODE": Counter(),
        "EXCLUDED_REASONS": Counter(),
    }
    for r in rows:
        out["POSITION_GROUP"][str(r.get("position_group") or "NULL")] += 1
        out["STATUS_CODE"][str(r.get("status_code") or "NULL")] += 1
        ok, reason = staff_is_eligible(r)
        if ok:
            out["ELIGIBLE"] += 1
        else:
            out["EXCLUDED"] += 1
            out["EXCLUDED_REASONS"][reason] += 1
    out["POSITION_GROUP"] = dict(out["POSITION_GROUP"])
    out["STATUS_CODE"] = dict(out["STATUS_CODE"])
    out["EXCLUDED_REASONS"] = dict(out["EXCLUDED_REASONS"])
    return out

def current_year_members_anywhere(conn):
    rows = conn.execute(
        """
        SELECT staff_member_id, school_id
        FROM staff_year_records
        WHERE school_year_id=?
        """,
        (CURRENT_YEAR_ID,)
    ).fetchall()
    d = defaultdict(set)
    for member_id, school_id in rows:
        d[int(member_id)].add(int(school_id))
    return d

def official_execution_hits(conn):
    hits = []
    if "school_merger_official_executions" not in get_tables(conn):
        return hits
    cur = conn.execute(
        """
        SELECT *
        FROM school_merger_official_executions
        WHERE target_school_id IN (?, ?)
           OR CAST(source_school_ids_json AS TEXT) LIKE ?
           OR CAST(source_school_ids_json AS TEXT) LIKE ?
        ORDER BY id
        """,
        (SOURCE_ID, TARGET_ID, f"%{SOURCE_ID}%", f"%{TARGET_ID}%")
    )
    names = [d[0] for d in cur.description]
    for row in cur.fetchall():
        hits.append(dict(zip(names, row)))
    return hits

def operation_hits(conn):
    hits = []
    if "school_merger_operations" not in get_tables(conn):
        return hits
    cur = conn.execute(
        """
        SELECT *
        FROM school_merger_operations
        WHERE target_school_id IN (?, ?)
           OR CAST(source_school_ids_json AS TEXT) LIKE ?
           OR CAST(source_school_ids_json AS TEXT) LIKE ?
        ORDER BY id
        """,
        (SOURCE_ID, TARGET_ID, f"%{SOURCE_ID}%", f"%{TARGET_ID}%")
    )
    names = [d[0] for d in cur.description]
    for row in cur.fetchall():
        hits.append(dict(zip(names, row)))
    return hits

def main():
    print("=" * 150)
    print("PREVIEW THCS MẬU ĐÔN -> PTDT BÁN TRÚ THCS THẠCH NGÀN")
    print(f"OFFICIAL OPERATION = {OFFICIAL_OPERATION_ID}")
    print("CHỈ ĐỌC - KHÔNG GHI DATABASE")
    print("=" * 150)

    db = find_db()
    sha_before = sha256_file(db)
    print("DATABASE =", db)
    print("SHA BEFORE =", sha_before)
    print("phocap.db-wal =", (db.parent / "phocap.db-wal").stat().st_size if (db.parent / "phocap.db-wal").exists() else 0)
    print("phocap.db-journal =", (db.parent / "phocap.db-journal").stat().st_size if (db.parent / "phocap.db-journal").exists() else 0)

    conn = sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True, timeout=30)
    conn.execute("PRAGMA query_only=ON")

    preview_ok = False

    try:
        print("\n1. DATABASE HEALTH")
        print("-" * 150)
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        fk = conn.execute("PRAGMA foreign_key_check").fetchall()
        print("integrity =", integrity)
        print("FK =", len(fk))
        if integrity != "ok" or fk:
            print("PREVIEW_READY = NO")
            print("LÝ DO = DATABASE HEALTH KHÔNG ĐẠT")
            return

        print("\n2. KHÓA ĐÚNG NGUỒN / ĐÍCH")
        print("-" * 150)
        src = lock_school(conn, SOURCE_ID, SOURCE_CODE, "Mậu Đôn", COMMUNE_ID)
        tgt = lock_school(conn, TARGET_ID, TARGET_CODE, "Thạch Ngàn", COMMUNE_ID)
        print("SOURCE:")
        print_json(src)
        print("TARGET:")
        print_json(tgt)

        if int(src.get("is_active", 0)) != 1:
            print("PREVIEW_READY = NO")
            print("LÝ DO = SOURCE KHÔNG ACTIVE")
            return
        if int(tgt.get("is_active", 0)) != 1:
            print("PREVIEW_READY = NO")
            print("LÝ DO = TARGET KHÔNG ACTIVE")
            return

        print("\n3. KIỂM TRA ĐÃ THỰC HIỆN TRƯỚC CHƯA")
        print("-" * 150)
        off_hits = official_execution_hits(conn)
        op_hits = operation_hits(conn)
        print("OFFICIAL_EXECUTION_HITS =", len(off_hits))
        if off_hits:
            print_json(off_hits)
        print("MERGER_OPERATION_HITS =", len(op_hits))
        if op_hits:
            print_json(op_hits)

        if off_hits:
            print("PREVIEW_READY = NO")
            print("LÝ DO = ĐÃ CÓ OFFICIAL EXECUTION LIÊN QUAN SOURCE/TARGET")
            return

        print("\n4. DẤU VẾT DỮ LIỆU NGUỒN / ĐÍCH")
        print("-" * 150)
        print("\nSOURCE FOOTPRINT:")
        print_json(footprint(conn, SOURCE_ID))
        print("\nTARGET FOOTPRINT:")
        print_json(footprint(conn, TARGET_ID))

        print("\n5. NHÂN SỰ NỀN 2025-2026")
        print("-" * 150)
        src_staff = staff_rows(conn, SOURCE_ID, PAST_YEAR_ID)
        tgt_staff = staff_rows(conn, TARGET_ID, PAST_YEAR_ID)

        src_sum = summarize_staff(src_staff)
        tgt_sum = summarize_staff(tgt_staff)

        print("SOURCE STAFF SUMMARY:")
        print_json(src_sum)
        print("TARGET STAFF SUMMARY:")
        print_json(tgt_sum)

        print("\n6. MÔ PHỎNG GỘP TOÀN TRƯỜNG VÀO TARGET NĂM 2026-2027")
        print("-" * 150)

        eligible_rows = []
        excluded_rows = []

        for origin, rows in (("SOURCE", src_staff), ("TARGET", tgt_staff)):
            for r in rows:
                ok, reason = staff_is_eligible(r)
                item = dict(r)
                item["_origin"] = origin
                if ok:
                    eligible_rows.append(item)
                else:
                    item["_exclude_reason"] = reason
                    excluded_rows.append(item)

        by_member = defaultdict(list)
        for r in eligible_rows:
            by_member[int(r["staff_member_id"])].append(r)

        duplicate_member_ids = sorted(
            member_id for member_id, rows in by_member.items()
            if len(rows) > 1
        )

        current_anywhere = current_year_members_anywhere(conn)
        already_current = {}
        to_create = []

        for member_id, rows in sorted(by_member.items()):
            if member_id in current_anywhere:
                already_current[member_id] = sorted(current_anywhere[member_id])
            else:
                to_create.append(member_id)

        # Phân loại theo position_group bằng một bản ghi đại diện / member.
        expected_categories = Counter()
        for member_id, rows in by_member.items():
            representative = rows[0]
            expected_categories[str(representative.get("position_group") or "NULL")] += 1

        print("ELIGIBLE ROWS SOURCE+TARGET =", len(eligible_rows))
        print("UNIQUE ELIGIBLE STAFF MEMBERS =", len(by_member))
        print("DUPLICATE MEMBER IDS BETWEEN SOURCE/TARGET =", duplicate_member_ids)
        print("ALREADY HAVE CURRENT-YEAR RECORD ANYWHERE =", len(already_current))
        if already_current:
            print_json(already_current)
        print("EXPECTED NEW CURRENT-YEAR RECORDS TO TARGET =", len(to_create))
        print("EXPECTED CATEGORY TOTALS (UNIQUE) =", dict(expected_categories))
        print("EXCLUDED ROWS =", len(excluded_rows))
        if excluded_rows:
            print_json(excluded_rows)

        print("\n7. KIỂM TRA TÀI KHOẢN TRƯỜNG")
        print("-" * 150)
        for sid, label in ((SOURCE_ID, "SOURCE"), (TARGET_ID, "TARGET")):
            cur = conn.execute(
                """
                SELECT id, username, full_name, role_id, commune_id, school_id, is_active, created_at
                FROM users
                WHERE school_id=?
                ORDER BY id
                """,
                (sid,)
            )
            names = [d[0] for d in cur.description]
            rows = [dict(zip(names, r)) for r in cur.fetchall()]
            print(label, "USERS:")
            print_json(rows)

        print("\n8. PREVIEW FINGERPRINT")
        print("-" * 150)
        fingerprint_payload = {
            "official_operation_id": OFFICIAL_OPERATION_ID,
            "source_school_id": SOURCE_ID,
            "source_code": SOURCE_CODE,
            "target_school_id": TARGET_ID,
            "target_code": TARGET_CODE,
            "past_year_id": PAST_YEAR_ID,
            "current_year_id": CURRENT_YEAR_ID,
            "source_staff": src_sum,
            "target_staff": tgt_sum,
            "unique_eligible_staff": len(by_member),
            "expected_new_current_year_records": len(to_create),
            "already_current_count": len(already_current),
            "duplicate_member_ids": duplicate_member_ids,
            "excluded_count": len(excluded_rows),
        }
        payload_text = json.dumps(
            fingerprint_payload,
            ensure_ascii=False,
            sort_keys=True,
            default=str
        )
        preview_fingerprint = hashlib.sha256(payload_text.encode("utf-8")).hexdigest()
        print("PREVIEW_FINGERPRINT =", preview_fingerprint)

        # Điều kiện READY: đúng nguồn/đích, chưa official, không trùng member giữa source-target.
        # Nếu đã có current-year staff ở nơi khác thì vẫn KHÔNG READY để tránh tự ý bỏ qua.
        reasons = []
        if duplicate_member_ids:
            reasons.append("Có staff_member_id trùng giữa SOURCE và TARGET năm nền")
        if already_current:
            reasons.append("Có staff_member_id đã có bản ghi năm 2026-2027 ở nơi khác")

        if reasons:
            print("\nPREVIEW_READY = NO")
            for r in reasons:
                print("LÝ DO =", r)
        else:
            preview_ok = True
            print("\nPREVIEW_READY = YES")
            print("MÔ HÌNH = THCS_MAU_DON_FULL_SOURCE_MERGE")
            print(f"SOURCE = {SOURCE_ID} | {SOURCE_CODE} | {SOURCE_NAME}")
            print(f"TARGET = {TARGET_ID} | {TARGET_CODE} | {TARGET_NAME}")
            print(f"OFFICIAL_OPERATION = {OFFICIAL_OPERATION_ID}")
            print("DATABASE = CHƯA GHI")
            print("BƯỚC SAU = CHỈ LÀM COMMIT SAU KHI ĐỌC KẾT QUẢ PREVIEW")

    finally:
        conn.close()

    sha_after = sha256_file(db)
    print("\n" + "=" * 150)
    print("FILE SAFETY")
    print("=" * 150)
    print("DB:", sha_before, "->", sha_after)

    if sha_before != sha_after:
        print("CẢNH BÁO: DATABASE ĐÃ THAY ĐỔI")
        sys.exit(3)

    print("\n" + "=" * 150)
    print("PREVIEW HOÀN TẤT")
    print("DATABASE = KHÔNG THAY ĐỔI")
    print("KHÔNG SÁP NHẬP")
    print("PREVIEW_READY =", "YES" if preview_ok else "NO")
    print("=" * 150)

if __name__ == "__main__":
    main()
