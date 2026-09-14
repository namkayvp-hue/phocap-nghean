import sys
import sqlite3
import hashlib
import json
from pathlib import Path
from datetime import datetime

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(r"C:\PhoCap")
DB = ROOT / "data" / "phocap.db"
BACKUPS = ROOT / "backups"
EXPORTS = ROOT / "exports" / "Sua_loi_staff_51394"

EXPECTED_DB_SHA = (
    "894ff0ab20fe77fb39bb393d70e41474"
    "ee9159e00c4ce81f05322f97ff7d86fe"
)

STAFF_ID = 51394
YEAR_RECORD_ID = 63788

TARGET_ID = 748
SOURCE_IDS = (750, 751)
PREVIOUS_IDS = (748, 750, 751)

def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            b = f.read(1024 * 1024)
            if not b:
                break
            h.update(b)
    return h.hexdigest()

def backup_sqlite(src_path, dst_path):
    src = sqlite3.connect(str(src_path))
    dst = sqlite3.connect(str(dst_path))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()

def db_health(path):
    con = sqlite3.connect(str(path))
    try:
        integrity = str(
            con.execute(
                "PRAGMA integrity_check"
            ).fetchone()[0]
        )

        fk = len(
            con.execute(
                "PRAGMA foreign_key_check"
            ).fetchall()
        )

        return integrity, fk

    finally:
        con.close()

print("=" * 120)
print("DON SACH HO SO KY THUAT SAI 51394")
print("STAFF_YEAR_RECORD 63788 - MN NGHI DIEN")
print("=" * 120)
print()
print("CHI TAC DONG:")
print(" - Xoa staff_year_records id=63788")
print(" - Xoa staff_members id=51394")
print()
print("KHONG TAC DONG:")
print(" - users")
print(" - truong 748 / 750 / 751")
print(" - lich su 2025-2026")
print(" - hoc sinh / lop / CSVC")
print(" - source code")
print("=" * 120)

# ============================================================
# 1. HASH + HEALTH TRUOC
# ============================================================

db_before = sha256(DB)

print()
print("DB SHA truoc:", db_before)

if db_before != EXPECTED_DB_SHA:
    raise RuntimeError(
        "DUNG: DB hash khong con dung nen da kiem tra. "
        "Khong duoc sua."
    )

integrity_before, fk_before = db_health(DB)

print("integrity truoc:", integrity_before)
print("FK truoc       :", fk_before)

if integrity_before.lower() != "ok":
    raise RuntimeError(
        "DUNG: integrity_check truoc sua != ok."
    )

if fk_before != 0:
    raise RuntimeError(
        "DUNG: DB dang co loi foreign key."
    )

# ============================================================
# 2. PRECHECK READ-ONLY
# ============================================================

ro = sqlite3.connect(
    DB.resolve().as_uri() + "?mode=ro",
    uri=True,
    timeout=30,
)
ro.row_factory = sqlite3.Row
ro.execute("PRAGMA query_only=ON")

years = {
    str(r["code"] or "")
    .replace("–", "-")
    .replace("—", "-")
    .strip(): int(r["id"])
    for r in ro.execute(
        "SELECT id,code FROM school_years"
    ).fetchall()
}

prev_year = years.get("2025-2026")
curr_year = years.get("2026-2027")

if prev_year is None or curr_year is None:
    raise RuntimeError(
        "Khong tim thay du nam hoc."
    )

member = ro.execute(
    """
    SELECT *
    FROM staff_members
    WHERE id=?
    """,
    (STAFF_ID,),
).fetchone()

if member is None:
    raise RuntimeError(
        "DUNG: staff_member 51394 khong con ton tai."
    )

m = dict(member)

required_member = {
    "id": 51394,
    "code": "NS-00051394",
    "ministry_staff_code": None,
    "full_name": "Trường Mầm non Nghi Hoa",
    "date_of_birth": None,
    "gender": None,
}

for key, expected in required_member.items():
    if m.get(key) != expected:
        raise RuntimeError(
            f"DUNG: staff_member 51394 thay doi tai {key}: "
            f"{m.get(key)!r} != {expected!r}"
        )

record = ro.execute(
    """
    SELECT *
    FROM staff_year_records
    WHERE id=?
    """,
    (YEAR_RECORD_ID,),
).fetchone()

if record is None:
    raise RuntimeError(
        "DUNG: year_record 63788 khong con ton tai."
    )

r = dict(record)

required_record = {
    "id": 63788,
    "staff_member_id": 51394,
    "school_year_id": curr_year,
    "school_id": 748,
    "status_code": "DANG_LAM_VIEC",
    "position_group": "CBQL",
    "created_by_user_id": 12933,
}

for key, expected in required_record.items():
    if r.get(key) != expected:
        raise RuntimeError(
            f"DUNG: year_record 63788 thay doi tai {key}: "
            f"{r.get(key)!r} != {expected!r}"
        )

user = ro.execute(
    """
    SELECT
        id,
        username,
        school_id,
        is_active
    FROM users
    WHERE id=12933
    """
).fetchone()

if user is None:
    raise RuntimeError(
        "DUNG: khong con user 12933."
    )

u = dict(user)

if (
    u.get("username") != "truong_40429325"
    or int(u.get("school_id") or 0) != 750
    or int(u.get("is_active") or 0) != 0
):
    raise RuntimeError(
        "DUNG: user truong Nghi Hoa khong con dung trang thai da kiem tra."
    )

# ------------------------------------------------------------
# Previous eligible set
# ------------------------------------------------------------

prev_rows = ro.execute(
    """
    SELECT
        syr.staff_member_id,
        syr.school_id,
        syr.status_code,
        syr.is_active
    FROM staff_year_records syr
    WHERE syr.school_year_id=?
      AND syr.school_id IN (748,750,751)
    """,
    (prev_year,),
).fetchall()

previous_ids = {
    int(x["staff_member_id"])
    for x in prev_rows
    if int(x["is_active"] or 0) == 1
    and str(x["status_code"] or "") == "DANG_LAM_VIEC"
}

if len(previous_ids) != 87:
    raise RuntimeError(
        f"DUNG: previous eligible={len(previous_ids)}, expected=87."
    )

# ------------------------------------------------------------
# Current target set
# ------------------------------------------------------------

current_rows = ro.execute(
    """
    SELECT
        staff_member_id
    FROM staff_year_records
    WHERE school_year_id=?
      AND school_id=748
      AND is_active=1
    """,
    (curr_year,),
).fetchall()

current_ids = {
    int(x["staff_member_id"])
    for x in current_rows
}

if len(current_ids) != 88:
    raise RuntimeError(
        f"DUNG: current target={len(current_ids)}, expected=88."
    )

extra_ids = current_ids - previous_ids
missing_ids = previous_ids - current_ids

print()
print("PRECHECK IDENTITY:")
print(" previous eligible =", len(previous_ids))
print(" current target    =", len(current_ids))
print(" extra current     =", sorted(extra_ids))
print(" missing current   =", sorted(missing_ids))

if extra_ids != {51394}:
    raise RuntimeError(
        "DUNG: ho so extra khong con duy nhat 51394."
    )

if missing_ids:
    raise RuntimeError(
        "DUNG: co nhan su nam truoc bi thieu o current."
    )

# ------------------------------------------------------------
# Reference count
# ------------------------------------------------------------

ref_count = int(
    ro.execute(
        """
        SELECT COUNT(*)
        FROM staff_year_records
        WHERE staff_member_id=?
        """,
        (STAFF_ID,),
    ).fetchone()[0]
)

if ref_count != 1:
    raise RuntimeError(
        f"DUNG: 51394 co {ref_count} staff_year_records, expected=1."
    )

ro.close()

print()
print("PRECHECK: PASS")

# ============================================================
# 3. BACKUP
# ============================================================

BACKUPS.mkdir(
    parents=True,
    exist_ok=True,
)

EXPORTS.mkdir(
    parents=True,
    exist_ok=True,
)

stamp = datetime.now().strftime(
    "%Y%m%d_%H%M%S"
)

backup_path = (
    BACKUPS
    / f"phocap_truoc_don_staff_51394_{stamp}.db"
)

backup_sqlite(
    DB,
    backup_path,
)

backup_integrity, backup_fk = db_health(
    backup_path
)

if backup_integrity.lower() != "ok":
    raise RuntimeError(
        "Backup integrity_check khong dat."
    )

if backup_fk != 0:
    raise RuntimeError(
        "Backup co loi foreign key."
    )

print()
print("BACKUP OK:")
print(backup_path)

# ============================================================
# 4. TRANSACTION SUA THAT
# ============================================================

con = sqlite3.connect(
    str(DB),
    timeout=30,
)
con.row_factory = sqlite3.Row
con.execute("PRAGMA foreign_keys=ON")

committed = False

try:
    con.execute("BEGIN IMMEDIATE")

    # Recheck trong transaction.
    row = con.execute(
        """
        SELECT
            id,
            staff_member_id,
            school_year_id,
            school_id
        FROM staff_year_records
        WHERE id=63788
        """
    ).fetchone()

    if row is None:
        raise RuntimeError(
            "Year record bien mat truoc DELETE."
        )

    if (
        int(row["staff_member_id"]) != 51394
        or int(row["school_year_id"]) != curr_year
        or int(row["school_id"]) != 748
    ):
        raise RuntimeError(
            "Year record 63788 khong con dung fingerprint."
        )

    # --------------------------------------------------------
    # DELETE CHILD FIRST
    # --------------------------------------------------------

    cur = con.execute(
        """
        DELETE FROM staff_year_records
        WHERE id=63788
          AND staff_member_id=51394
          AND school_year_id=?
          AND school_id=748
        """,
        (curr_year,),
    )

    if cur.rowcount != 1:
        raise RuntimeError(
            f"DELETE year_record rowcount={cur.rowcount}, expected=1."
        )

    # --------------------------------------------------------
    # DELETE MASTER
    # --------------------------------------------------------

    cur = con.execute(
        """
        DELETE FROM staff_members
        WHERE id=51394
          AND code='NS-00051394'
          AND ministry_staff_code IS NULL
          AND full_name='Trường Mầm non Nghi Hoa'
          AND date_of_birth IS NULL
          AND gender IS NULL
        """
    )

    if cur.rowcount != 1:
        raise RuntimeError(
            f"DELETE staff_member rowcount={cur.rowcount}, expected=1."
        )

    # ========================================================
    # 5. VERIFY BEFORE COMMIT
    # ========================================================

    left_member = int(
        con.execute(
            """
            SELECT COUNT(*)
            FROM staff_members
            WHERE id=51394
            """
        ).fetchone()[0]
    )

    left_record = int(
        con.execute(
            """
            SELECT COUNT(*)
            FROM staff_year_records
            WHERE id=63788
               OR staff_member_id=51394
            """
        ).fetchone()[0]
    )

    if left_member != 0 or left_record != 0:
        raise RuntimeError(
            "Sau DELETE van con dau vet 51394/63788."
        )

    after_rows = con.execute(
        """
        SELECT
            staff_member_id
        FROM staff_year_records
        WHERE school_year_id=?
          AND school_id=748
          AND is_active=1
        """,
        (curr_year,),
    ).fetchall()

    after_ids = {
        int(x["staff_member_id"])
        for x in after_rows
    }

    print()
    print("VERIFY TRUOC COMMIT:")
    print(
        " current Nghi Dien =",
        len(after_ids),
    )

    if len(after_ids) != 87:
        raise RuntimeError(
            f"Nghi Dien sau sua={len(after_ids)}, expected=87."
        )

    if after_ids != previous_ids:
        raise RuntimeError(
            "Identity Nghi Dien sau sua khong khop "
            "87 previous eligible."
        )

    # Nguon 750/751 nam hien hanh van phai = 0.
    source_current = int(
        con.execute(
            """
            SELECT COUNT(*)
            FROM staff_year_records
            WHERE school_year_id=?
              AND school_id IN (750,751)
            """,
            (curr_year,),
        ).fetchone()[0]
    )

    if source_current != 0:
        raise RuntimeError(
            f"Nguon 750/751 current residual={source_current}, expected=0."
        )

    fk_errors = con.execute(
        "PRAGMA foreign_key_check"
    ).fetchall()

    if fk_errors:
        raise RuntimeError(
            f"foreign_key_check truoc COMMIT co {len(fk_errors)} loi."
        )

    integrity = str(
        con.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]
    )

    if integrity.lower() != "ok":
        raise RuntimeError(
            f"integrity_check truoc COMMIT={integrity}"
        )

    con.commit()
    committed = True

except Exception:
    if not committed:
        try:
            con.rollback()
        except Exception:
            pass
    raise

finally:
    con.close()

# ============================================================
# 6. VERIFY AFTER COMMIT
# ============================================================

integrity_after, fk_after = db_health(
    DB
)

if integrity_after.lower() != "ok":
    raise RuntimeError(
        "DA COMMIT nhung integrity_check sau sua != ok. "
        f"Khoi phuc tu backup: {backup_path}"
    )

if fk_after != 0:
    raise RuntimeError(
        "DA COMMIT nhung foreign_key_check sau sua co loi. "
        f"Khoi phuc tu backup: {backup_path}"
    )

check = sqlite3.connect(
    DB.resolve().as_uri() + "?mode=ro",
    uri=True,
)
check.row_factory = sqlite3.Row
check.execute("PRAGMA query_only=ON")

final_total = int(
    check.execute(
        """
        SELECT COUNT(*)
        FROM staff_year_records
        WHERE school_year_id=?
          AND school_id=748
          AND is_active=1
        """,
        (curr_year,),
    ).fetchone()[0]
)

final_cbql = int(
    check.execute(
        """
        SELECT COUNT(*)
        FROM staff_year_records
        WHERE school_year_id=?
          AND school_id=748
          AND is_active=1
          AND position_group='CBQL'
        """,
        (curr_year,),
    ).fetchone()[0]
)

final_gv = int(
    check.execute(
        """
        SELECT COUNT(*)
        FROM staff_year_records
        WHERE school_year_id=?
          AND school_id=748
          AND is_active=1
          AND position_group='GIAO_VIEN'
        """,
        (curr_year,),
    ).fetchone()[0]
)

final_nv = int(
    check.execute(
        """
        SELECT COUNT(*)
        FROM staff_year_records
        WHERE school_year_id=?
          AND school_id=748
          AND is_active=1
          AND position_group='NHAN_VIEN'
        """,
        (curr_year,),
    ).fetchone()[0]
)

user_after = check.execute(
    """
    SELECT
        id,
        username,
        school_id,
        is_active
    FROM users
    WHERE id=12933
    """
).fetchone()

check.close()

if final_total != 87:
    raise RuntimeError(
        f"Final Nghi Dien={final_total}, expected=87."
    )

if user_after is None:
    raise RuntimeError(
        "User 12933 bi mat ngoai du kien."
    )

db_after = sha256(DB)

report = {
    "status": "SUCCESS",
    "action": "REMOVE_FALSE_STAFF_51394",
    "staff_member_id_removed": 51394,
    "staff_year_record_id_removed": 63788,
    "target_school_id": 748,
    "target_school": "Trường Mầm non Nghi Diên",
    "school_year": "2026-2027",
    "previous_eligible": 87,
    "before_current_total": 88,
    "after_current_total": final_total,
    "after_cbql": final_cbql,
    "after_teacher": final_gv,
    "after_employee": final_nv,
    "school_login_12933_preserved": True,
    "backup": str(backup_path),
    "integrity_after": integrity_after,
    "foreign_key_errors_after": fk_after,
    "db_sha256_before": db_before,
    "db_sha256_after": db_after,
}

report_path = (
    EXPORTS
    / f"ket_qua_don_staff_51394_{stamp}.json"
)

report_path.write_text(
    json.dumps(
        report,
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8",
)

print()
print("=" * 120)
print("DON SACH THANH CONG")
print("=" * 120)

print(
    "Da xoa staff_year_record :",
    63788,
)

print(
    "Da xoa staff_member      :",
    51394,
)

print(
    "MN Nghi Dien 2026-2027   :",
    final_total,
)

print(
    "Co cau hien tai          :",
    f"CBQL={final_cbql} | GV={final_gv} | NV={final_nv}",
)

print(
    "Identity 87 nguoi        : KHOP 100% VOI previous eligible"
)

print(
    "User truong Nghi Hoa     : GIU NGUYEN"
)

print(
    "Nguon 750/751            : KHONG MO KHOA"
)

print(
    "integrity_check          :",
    integrity_after,
)

print(
    "foreign_key_check        :",
    fk_after,
)

print()
print("DB SHA truoc:", db_before)
print("DB SHA sau  :", db_after)

print()
print("Backup :", backup_path)
print("Report :", report_path)

print("=" * 120)
