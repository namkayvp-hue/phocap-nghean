from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sqlite3

PACKAGE = Path(__file__).resolve().parent
PROJECT = Path(os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap"))
DB = PROJECT / "data" / "phocap.db"
MANIFEST = json.loads((PACKAGE / "manifest.json").read_text(encoding="utf-8"))

EXPECTED_COLUMNS = {
    "id", "school_id", "report_year", "item_code", "amount",
    "note", "updated_by_user_id", "updated_at",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    print("=" * 118)
    print("BÀI 33A - READ ONLY AUDIT TÀI CHÍNH TRƯỜNG -> XÃ/SỞ")
    print("=" * 118)
    print("PROJECT =", PROJECT)
    print("DB =", DB)

    db_sha_before = sha256(DB)
    source_ok = True
    for rel, expected in MANIFEST["expected_after"].items():
        path = PROJECT / rel
        actual = sha256(path) if path.is_file() else "MISSING"
        print(f"SHA {rel} = {actual}")
        if actual != expected:
            source_ok = False

    # Chỉ đọc DB bằng URI mode=ro.
    uri = DB.resolve().as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True) as con:
        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
        fk_count = len(con.execute("PRAGMA foreign_key_check").fetchall())
        table_exists = con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='school_finance_report_values'"
        ).fetchone() is not None
        cols = {row[1] for row in con.execute(
            'PRAGMA table_info("school_finance_report_values")'
        ).fetchall()} if table_exists else set()
        rows = con.execute(
            "SELECT COUNT(*) FROM school_finance_report_values"
        ).fetchone()[0] if table_exists else -1

    markers = {
        "SCHOOL_ROLE_ROUTE": "role == SCHOOL_ROLE_CODE",
        "SCHOOL_OWN_SCOPE": "school_id != own_school_id",
        "AGGREGATE_SERVICE": "load_finance_values",
        "MENU_TRUONG": "['ADMIN', 'SO', 'XA', 'TRUONG']",
        "MN_TC_EXPORT": "fill_finance_worksheet",
    }
    marker_files = {
        "SCHOOL_ROLE_ROUTE": PROJECT / "app/routers/report_inputs.py",
        "SCHOOL_OWN_SCOPE": PROJECT / "app/routers/report_inputs.py",
        "AGGREGATE_SERVICE": PROJECT / "app/services/finance_school_service.py",
        "MENU_TRUONG": PROJECT / "app/templates/partials/dropdown_menu_v1.html",
        "MN_TC_EXPORT": PROJECT / "app/routers/pcgdmn_template_report.py",
    }
    marker_ok = True
    for key, needle in markers.items():
        path = marker_files[key]
        ok = path.is_file() and needle in path.read_text(encoding="utf-8")
        print(f"{key} =", "YES" if ok else "NO")
        marker_ok = marker_ok and ok

    db_sha_after = sha256(DB)
    schema_ok = table_exists and EXPECTED_COLUMNS.issubset(cols)

    print("INTEGRITY =", integrity)
    print("FK_COUNT =", fk_count)
    print("TABLE_EXISTS =", "YES" if table_exists else "NO")
    print("TABLE_SCHEMA_OK =", "YES" if schema_ok else "NO")
    print("SCHOOL_FINANCE_ROWS =", rows)
    print("SOURCE_SHA_OK =", "YES" if source_ok else "NO")
    print("MARKERS_OK =", "YES" if marker_ok else "NO")
    print("DATABASE_WRITES_THIS_RUN = 0")
    print("DB_SHA_UNCHANGED =", "YES" if db_sha_before == db_sha_after else "NO")

    success = (
        source_ok
        and marker_ok
        and integrity == "ok"
        and fk_count == 0
        and schema_ok
        and db_sha_before == db_sha_after
    )
    print("AUDIT33A_SUCCESS =", "YES" if success else "NO")
    print("=" * 118)


if __name__ == "__main__":
    main()
