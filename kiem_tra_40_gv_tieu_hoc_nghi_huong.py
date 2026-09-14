from __future__ import annotations

import os
import re
import sqlite3
import sys
import unicodedata
from pathlib import Path

PROJECT = Path(os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")).resolve()
sys.path.insert(0, str(PROJECT))

from app.database import DATABASE_PATH

DB = Path(DATABASE_PATH)
SCHOOL_NAME = os.environ.get("PHOCAP_TEST_SCHOOL", "Tiểu học Nghi Hương")
BATCH_ID = int(os.environ.get("PHOCAP_TEST_BATCH", "3"))


def norm(value: object) -> str:
    raw = str(value or "").strip().lower()
    raw = unicodedata.normalize("NFD", raw)
    raw = "".join(ch for ch in raw if unicodedata.category(ch) != "Mn")
    return re.sub(r"\s+", " ", raw)


con = sqlite3.connect(str(DB))
con.row_factory = sqlite3.Row

school = con.execute(
    """
    SELECT id, name, commune_id
    FROM schools
    WHERE name = ?
    LIMIT 1
    """,
    (SCHOOL_NAME,),
).fetchone()

if not school:
    raise SystemExit(f"Không tìm thấy trường: {SCHOOL_NAME}")

batch = con.execute(
    """
    SELECT sb.id, sb.school_year_id, sy.code AS school_year_code
    FROM survey_batches sb
    JOIN school_years sy ON sy.id = sb.school_year_id
    WHERE sb.id = ?
    LIMIT 1
    """,
    (BATCH_ID,),
).fetchone()

if not batch:
    raise SystemExit(f"Không tìm thấy đợt điều tra #{BATCH_ID}")

m = re.search(r"(\d{4})", str(batch["school_year_code"] or ""))
target_start = int(m.group(1)) if m else 9999

staff_rows = con.execute(
    """
    SELECT
        syr.id AS record_id,
        sm.id AS staff_member_id,
        sm.ministry_staff_code,
        sm.code AS internal_staff_code,
        sm.full_name,
        sy.code AS source_year_code,
        CAST(SUBSTR(sy.code, 1, 4) AS INTEGER) AS source_year_start
    FROM staff_year_records syr
    JOIN staff_members sm ON sm.id = syr.staff_member_id
    JOIN school_years sy ON sy.id = syr.school_year_id
    WHERE syr.school_id = ?
      AND syr.is_active = 1
      AND sm.is_active = 1
      AND UPPER(syr.position_group) = 'GIAO_VIEN'
      AND UPPER(syr.status_code) = 'DANG_LAM_VIEC'
      AND CAST(SUBSTR(sy.code, 1, 4) AS INTEGER) <= ?
    ORDER BY sm.id, source_year_start DESC, syr.id DESC
    """,
    (int(school["id"]), target_start),
).fetchall()

latest_staff = []
seen = set()
for row in staff_rows:
    sid = int(row["staff_member_id"])
    if sid in seen:
        continue
    seen.add(sid)
    latest_staff.append(row)

active_users = con.execute(
    """
    SELECT u.id, u.username, u.full_name, u.school_id, u.is_active,
           UPPER(r.code) AS role_code
    FROM users u
    JOIN roles r ON r.id = u.role_id
    WHERE u.school_id = ?
      AND UPPER(r.code) = 'GIAO_VIEN'
    ORDER BY u.full_name COLLATE NOCASE, u.id
    """,
    (int(school["id"]),),
).fetchall()

active_only = [u for u in active_users if int(u["is_active"] or 0) == 1]

print("=" * 105)
print("KIỂM TRA ĐỐI CHIẾU HỒ SƠ ĐỘI NGŨ ↔ TÀI KHOẢN GIÁO VIÊN")
print("=" * 105)
print("Trường:", school["name"], "| ID:", school["id"])
print("Đợt:", batch["id"], "| Năm học:", batch["school_year_code"])
print("Hồ sơ GV đang làm việc:", len(latest_staff))
print("Tài khoản GIAO_VIEN của trường:", len(active_users))
print("Tài khoản GIAO_VIEN đang hoạt động:", len(active_only))
print()

by_username = {str(u["username"]).lower(): u for u in active_users}
by_name = {}
for u in active_users:
    by_name.setdefault(norm(u["full_name"]), []).append(u)

missing = []
locked = []
mismatch = []

for s in latest_staff:
    code = str(s["ministry_staff_code"] or s["internal_staff_code"] or "").strip()
    expected = f"gv.{code}".lower() if code else ""
    exact = by_username.get(expected) if expected else None

    if exact is not None:
        if int(exact["is_active"] or 0) != 1:
            locked.append((s, exact, "Đúng username theo mã nhưng tài khoản đang khóa"))
        continue

    same_name = by_name.get(norm(s["full_name"]), [])
    if len(same_name) == 1:
        u = same_name[0]
        if int(u["is_active"] or 0) == 1:
            mismatch.append((s, u, "Khớp họ tên nhưng username không khớp mã GV"))
        else:
            locked.append((s, u, "Khớp họ tên nhưng tài khoản đang khóa"))
        continue

    missing.append(s)

print("=== HỒ SƠ CHƯA CÓ TÀI KHOẢN KHỚP ===")
if not missing:
    print("Không có.")
else:
    for i, s in enumerate(missing, 1):
        code = str(s["ministry_staff_code"] or s["internal_staff_code"] or "")
        print(f"{i}. {s['full_name']} | Mã: {code} | Nguồn: {s['source_year_code']}")

print()
print("=== TÀI KHOẢN ĐANG KHÓA ===")
if not locked:
    print("Không có.")
else:
    for i, (s, u, note) in enumerate(locked, 1):
        print(f"{i}. {s['full_name']} | Mã GV: {s['ministry_staff_code'] or s['internal_staff_code']} "
              f"| User: {u['username']} | {note}")

print()
print("=== KHỚP HỌ TÊN NHƯNG USERNAME KHÔNG KHỚP MÃ GV ===")
if not mismatch:
    print("Không có.")
else:
    for i, (s, u, note) in enumerate(mismatch, 1):
        print(f"{i}. {s['full_name']} | Mã GV: {s['ministry_staff_code'] or s['internal_staff_code']} "
              f"| User hiện có: {u['username']} | {note}")

print()
print("=== TÀI KHOẢN GV ĐANG HOẠT ĐỘNG ===")
for i, u in enumerate(active_only, 1):
    print(f"{i:02d}. {u['full_name']} | {u['username']}")

print()
print("KẾT LUẬN:")
print("- Script chỉ đọc dữ liệu, KHÔNG sửa database.")
print("- Hãy gửi toàn bộ kết quả PowerShell cho ChatGPT nếu số hồ sơ và số tài khoản vẫn không khớp.")
