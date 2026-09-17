from __future__ import annotations

import hashlib
import re
import sys
from datetime import date
from io import BytesIO
from pathlib import Path

from openpyxl import Workbook
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

PROJECT = Path(r"C:\PhoCap")
DB_PATH = PROJECT / "data" / "phocap.db"
ROUTE_PATH = PROJECT / "app" / "routers" / "student_reconciliation_source.py"
HELPER_PATH = PROJECT / "app" / "services" / "school_name_history.py"

EXPECTED_ROUTE_SHA = "384339cae03a207b7019eeaa315683135489385745a4de0c03c0d3497cd21ede"
EXPECTED_HELPER_SHA = "ca1a61ef4da4b9ef7e2ea70d4f6ff212112a5d00bd1943ae74e625d87734349d"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def year_start(value: str | None) -> int | None:
    m = re.search(r"(\d{4})\D+(\d{4})", str(value or ""))
    if not m:
        return None
    a, b = int(m.group(1)), int(m.group(2))
    return a if b == a + 1 else None


def make_workbook(school_name: str, code_suffix: str) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "32C_DRY_RUN"
    ws.append([
        "Trường",
        "Lớp",
        "Mã định danh Bộ GD&ĐT",
        "Họ tên",
        "Ngày sinh",
        "Giới tính",
        "Trạng thái",
    ])
    ws.append([
        school_name,
        "TEST-32C",
        f"DRYRUN32C{code_suffix}",
        "HỌC SINH KIỂM THỬ 32C",
        date(2012, 1, 1),
        "Nam",
        "Đang học",
    ])
    bio = BytesIO()
    wb.save(bio)
    return bio.getvalue()


def main() -> int:
    print("=" * 118)
    print("BAI 32C - DRY-RUN NGUON HOC SINH THEO TEN TRUONG LICH SU")
    print("READ ONLY - KHONG GHI DATABASE - KHONG SUA SOURCE")
    print("=" * 118)

    for path, label in ((DB_PATH, "DB"), (ROUTE_PATH, "ROUTE"), (HELPER_PATH, "HELPER")):
        if not path.exists():
            print(f"STOP: {label} NOT FOUND = {path}")
            return 2

    route_sha = sha256_file(ROUTE_PATH)
    helper_sha = sha256_file(HELPER_PATH)
    db_sha_before = sha256_file(DB_PATH)
    print(f"DB = {DB_PATH}")
    print(f"DB_SHA_BEFORE = {db_sha_before}")
    print(f"ROUTE_SHA = {route_sha}")
    print(f"HELPER_SHA = {helper_sha}")

    if route_sha != EXPECTED_ROUTE_SHA:
        print("STOP: ROUTE SHA KHONG DUNG NEN 32B DA KIEM TOAN.")
        return 3
    if helper_sha != EXPECTED_HELPER_SHA:
        print("STOP: HELPER SHA KHONG DUNG NEN 32B DA KIEM TOAN.")
        return 4

    sys.path.insert(0, str(PROJECT))
    from app.routers.student_reconciliation_source import _parse_workbook

    # Open SQLite in read-only mode. This makes accidental writes impossible.
    ro_url = f"sqlite:///file:{DB_PATH.as_posix()}?mode=ro&uri=true"
    engine = create_engine(ro_url, connect_args={"check_same_thread": False}, echo=False)

    total = 0
    passed = 0
    failed = 0
    first_case_details = None

    with Session(engine, autoflush=False, expire_on_commit=False) as db:
        integrity = db.execute(text("PRAGMA integrity_check")).scalar_one()
        fk_count = len(db.execute(text("PRAGMA foreign_key_check")).all())
        print(f"INTEGRITY = {integrity}")
        print(f"FK_COUNT = {fk_count}")
        if str(integrity).lower() != "ok" or fk_count != 0:
            print("STOP: DATABASE KHONG DAT KIEM TRA AN TOAN.")
            return 5

        histories = db.execute(text("""
            SELECT h.id, h.school_id, h.effective_school_year_id,
                   h.old_name, h.new_name,
                   y.code AS effective_year_code,
                   s.code AS school_code, s.name AS current_name,
                   s.commune_id
            FROM school_name_histories h
            JOIN school_years y ON y.id=h.effective_school_year_id
            JOIN schools s ON s.id=h.school_id
            ORDER BY h.id ASC
        """)).mappings().all()

        print(f"HISTORY_COUNT = {len(histories)}")
        print("--- PARSER DRY-RUN ---")

        for h in histories:
            eff_start = year_start(h["effective_year_code"])
            if eff_start is None:
                print(f"ID={h['id']} RESULT=FAIL REASON=INVALID_EFFECTIVE_YEAR")
                failed += 1
                total += 1
                continue

            prev_code = f"{eff_start - 1}-{eff_start}"
            prev_year = db.execute(
                text("SELECT id,code FROM school_years WHERE code=:code LIMIT 1"),
                {"code": prev_code},
            ).mappings().first()
            if prev_year is None:
                print(f"ID={h['id']} RESULT=FAIL REASON=PREVIOUS_YEAR_NOT_FOUND CODE={prev_code}")
                failed += 1
                total += 1
                continue

            # A. File source of the previous school year uses the OLD name.
            total += 1
            content_old = make_workbook(str(h["old_name"]), f"_{h['id']}_OLD")
            parsed_old = _parse_workbook(
                db,
                content_old,
                int(h["commune_id"]),
                int(prev_year["id"]),
            )
            old_ok = (
                not parsed_old.get("errors")
                and len(parsed_old.get("records", [])) == 1
                and int(parsed_old["records"][0]["school_id"]) == int(h["school_id"])
                and str(parsed_old["records"][0]["school_name_db"]) == str(h["old_name"])
            )
            if old_ok:
                passed += 1
            else:
                failed += 1

            # B. From the effective year, the NEW name must resolve to the same school_id.
            total += 1
            content_new = make_workbook(str(h["new_name"]), f"_{h['id']}_NEW")
            parsed_new = _parse_workbook(
                db,
                content_new,
                int(h["commune_id"]),
                int(h["effective_school_year_id"]),
            )
            new_ok = (
                not parsed_new.get("errors")
                and len(parsed_new.get("records", [])) == 1
                and int(parsed_new["records"][0]["school_id"]) == int(h["school_id"])
                and str(parsed_new["records"][0]["school_name_db"]) == str(h["new_name"])
            )
            if new_ok:
                passed += 1
            else:
                failed += 1

            print(
                f"ID={h['id']} SCHOOL_ID={h['school_id']} CODE={h['school_code']} "
                f"COMMUNE_ID={h['commune_id']}"
            )
            print(f"  {prev_code} OLD='{h['old_name']}' -> {'PASS' if old_ok else 'FAIL'}")
            if not old_ok:
                print(f"    ERRORS={parsed_old.get('errors', [])[:3]}")
                print(f"    RECORDS={parsed_old.get('records', [])[:1]}")
            print(
                f"  {h['effective_year_code']} NEW='{h['new_name']}' -> "
                f"{'PASS' if new_ok else 'FAIL'}"
            )
            if not new_ok:
                print(f"    ERRORS={parsed_new.get('errors', [])[:3]}")
                print(f"    RECORDS={parsed_new.get('records', [])[:1]}")

            if int(h["school_id"]) == 1594:
                first_case_details = {
                    "prev_code": prev_code,
                    "old_name": h["old_name"],
                    "old_ok": old_ok,
                    "effective": h["effective_year_code"],
                    "new_name": h["new_name"],
                    "new_ok": new_ok,
                    "resolved_old_school_id": (
                        parsed_old["records"][0]["school_id"]
                        if parsed_old.get("records") else None
                    ),
                }

        print("--- CA CHOT THCS CAM MUON / THCS MUONG QUANG ---")
        if first_case_details:
            d = first_case_details
            print(f"SOURCE_YEAR = {d['prev_code']}")
            print(f"EXCEL_NAME = {d['old_name']}")
            print(f"RESOLVED_SCHOOL_ID = {d['resolved_old_school_id']}")
            print(f"OLD_NAME_RESULT = {'PASS' if d['old_ok'] else 'FAIL'}")
            print(f"EFFECTIVE_YEAR = {d['effective']}")
            print(f"NEW_NAME = {d['new_name']}")
            print(f"NEW_NAME_RESULT = {'PASS' if d['new_ok'] else 'FAIL'}")
        else:
            print("RESULT = FAIL - KHONG TIM THAY SCHOOL_ID 1594 TRONG LICH SU DOI TEN")
            failed += 1

        tri_le = db.execute(text("""
            SELECT s.id,s.code,s.name,s.commune_id,
                   (SELECT COUNT(*) FROM school_name_histories h WHERE h.school_id=s.id) AS history_count
            FROM schools s WHERE s.code='40415412' LIMIT 1
        """)).mappings().first()
        print("--- TRI LE STATUS ---")
        if tri_le:
            print(f"TRI_LE_ID = {tri_le['id']}")
            print(f"TRI_LE_CURRENT_NAME = {tri_le['name']}")
            print(f"TRI_LE_HISTORY_COUNT = {tri_le['history_count']}")
        else:
            print("TRI_LE = NOT_FOUND")

    engine.dispose()

    db_sha_after = sha256_file(DB_PATH)
    print("--- SUMMARY ---")
    print(f"TESTS_TOTAL = {total}")
    print(f"TESTS_PASS = {passed}")
    print(f"TESTS_FAIL = {failed}")
    print("DATABASE_WRITES_THIS_RUN = 0")
    print(f"DB_SHA_AFTER = {db_sha_after}")
    print(f"DB_SHA_UNCHANGED = {'YES' if db_sha_before == db_sha_after else 'NO'}")

    success = (
        failed == 0
        and total > 0
        and db_sha_before == db_sha_after
        and first_case_details is not None
        and bool(first_case_details.get("old_ok"))
        and bool(first_case_details.get("new_ok"))
    )
    print(f"DRY_RUN_32C_SUCCESS = {'YES' if success else 'NO'}")
    print("=" * 118)
    return 0 if success else 10


if __name__ == "__main__":
    raise SystemExit(main())
