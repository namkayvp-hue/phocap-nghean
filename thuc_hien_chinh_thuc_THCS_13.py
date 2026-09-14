# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
import traceback
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(r"C:\PhoCap")

DB = ROOT / "data" / "phocap.db"
SERVICE = ROOT / "app" / "services" / "school_merger_level_batch_service.py"
ENGINE = ROOT / "app" / "services" / "school_merger_service.py"
ROSTER = ROOT / "data" / "school_merger_source_rosters" / "THCS_2025_2026.json"
RESOLUTION = ROOT / "data" / "school_merger_registry" / "qd3805_thcs_resolution.json"
HISTORY = ROOT / "data" / "school_merger_approved_plans.json"

EXPECTED_FILES = {
    "db": (
        DB,
        "882e4925fd3e39d7e097ce127612c093852075e608d3f937294135282afec75a",
    ),
    "level_service": (
        SERVICE,
        "9104fb99c78755e9eec86d090659b3a922834ff097d7292aa4d4b29e360a27f9",
    ),
    "engine": (
        ENGINE,
        "414fb49a4c5f4fed7b571cc55df381678fe660cd8a675ecaa2f6fd70ebd7827a",
    ),
    "roster": (
        ROSTER,
        "926528e0ae600a6b950b459c6f8ec5c6810e69d49158d1ff3c9a3d76c0bca657",
    ),
    "resolution": (
        RESOLUTION,
        "d9d347b19de0795553c8f047cb91a430ded63d9232ac7eda7ea069b716c2c0f4",
    ),
    "history": (
        HISTORY,
        "4e2c5f044c48c57dda40fecc11f4e9f466f236aacc082f224536b1685cadb1fc",
    ),
}

EXPECTED_BATCH_FINGERPRINT = (
    "845bc40d03b10def4a8d42916260468f7d58e1174b796d33d946340754fe85d3"
)

EXPECTED_PLAN_IDS = {
    "PA2026-1DF7D2567825",  # OP0026
    "PA2026-5DD3FA2B0840",  # OP0027
    "PA2026-440298C0FCC6",  # OP0028
    "PA2026-3E857A509786",  # OP0011
    "PA2026-5766BDC4F12D",  # OP0014
    "PA2026-1B5A34D3C68D",  # OP0042
    "PA2026-EA5959CE3A8C",  # OP0043
    "PA2026-98A8AEFB7088",  # OP0050
    "PA2026-11781F068A55",  # OP0051
    "PA2026-5F0387B33D01",  # OP0061
    "PA2026-F4E971245B82",  # OP0068
    "PA2026-4C15EEC22C47",  # OP0034
    "PA2026-853BD99FB835",  # OP0035
}

YEAR_ID = 2
LEVEL = "THCS"
ADMIN_USERNAME = "admin.sogddt"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def ro_connect() -> sqlite3.Connection:
    uri = DB.resolve().as_uri() + "?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    con.row_factory = sqlite3.Row
    return con


def table_exists(con: sqlite3.Connection, table: str) -> bool:
    row = con.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type='table' AND name=?
        LIMIT 1
        """,
        (table,),
    ).fetchone()
    return row is not None


def wal_journal_gate() -> None:
    for suffix in ("-wal", "-journal"):
        p = Path(str(DB) + suffix)
        size = p.stat().st_size if p.exists() else 0
        print(f"{p.name:24s} = {size}")
        if size != 0:
            raise RuntimeError(
                f"DUNG: {p.name} dang co {size} bytes. "
                "Khong thuc hien khi database con WAL/JOURNAL."
            )


def hash_gate() -> dict[str, str]:
    result = {}

    for label, (path, expected) in EXPECTED_FILES.items():
        if not path.exists():
            raise RuntimeError(f"DUNG: khong tim thay {path}")

        current = sha256(path)
        result[label] = current

        print(f"{label:14s} = {current}")

        if current != expected:
            raise RuntimeError(
                f"DUNG: SHA {label} da thay doi.\n"
                f"Expected: {expected}\n"
                f"Current : {current}"
            )

    return result


def load_actor() -> dict:
    con = ro_connect()
    try:
        row = con.execute(
            "SELECT * FROM users WHERE username=? LIMIT 1",
            (ADMIN_USERNAME,),
        ).fetchone()

        if row is None:
            raise RuntimeError(
                f"DUNG: khong tim thay tai khoan {ADMIN_USERNAME}"
            )

        data = dict(row)

        if data.get("id") is None:
            raise RuntimeError("DUNG: tai khoan admin khong co id.")

        if "is_active" in data and not bool(data.get("is_active")):
            raise RuntimeError("DUNG: tai khoan admin dang bi khoa.")

        return {
            "id": int(data["id"]),
            "username": str(data.get("username") or ADMIN_USERNAME),
            "full_name": str(data.get("full_name") or ""),
            "role_code": str(data.get("role_code") or ""),
        }
    finally:
        con.close()


def validate_preview(service):
    preview = service.build_level_batch_preview(
        school_year_id=YEAR_ID,
        level_code=LEVEL,
    )

    counts = dict(preview.get("counts") or {})
    candidates = list(preview.get("candidates") or [])
    candidate_plan_ids = {
        str(x.get("plan_id") or "").strip()
        for x in candidates
        if str(x.get("plan_id") or "").strip()
    }

    print("counts                =", counts)
    print("candidate_count       =", len(candidates))
    print(
        "effective_block_count =",
        preview.get("effective_block_count"),
    )
    print(
        "ready_for_execution   =",
        preview.get("ready_for_execution"),
    )
    print(
        "previous_batch        =",
        bool(preview.get("previous_batch")),
    )
    print(
        "overlap_items         =",
        preview.get("overlap_items") or [],
    )
    print(
        "extra_blockers        =",
        preview.get("extra_blockers") or [],
    )
    print(
        "batch_fingerprint     =",
        preview.get("batch_fingerprint"),
    )

    if counts != {
        "KEEP": 36,
        "DONE": 84,
        "READY": 13,
        "BLOCK": 0,
    }:
        raise RuntimeError(
            "DUNG: counts khong con dung 36/84/13/0."
        )

    if len(candidates) != 13:
        raise RuntimeError(
            "DUNG: candidate_count khong con bang 13."
        )

    if candidate_plan_ids != EXPECTED_PLAN_IDS:
        print("EXPECTED =", sorted(EXPECTED_PLAN_IDS))
        print("CURRENT  =", sorted(candidate_plan_ids))
        raise RuntimeError(
            "DUNG: danh sach 13 plan da thay doi."
        )

    if not preview.get("ready_for_execution"):
        raise RuntimeError(
            "DUNG: ready_for_execution != True."
        )

    if int(preview.get("effective_block_count") or 0) != 0:
        raise RuntimeError(
            "DUNG: effective_block_count != 0."
        )

    if preview.get("previous_batch") is not None:
        raise RuntimeError(
            "DUNG: THCS da co batch truoc do. TUYET DOI KHONG CHAY LAI."
        )

    if preview.get("overlap_items"):
        raise RuntimeError(
            "DUNG: van con overlap."
        )

    if preview.get("extra_blockers"):
        raise RuntimeError(
            "DUNG: van con extra_blockers."
        )

    current_fp = str(
        preview.get("batch_fingerprint") or ""
    )

    if current_fp != EXPECTED_BATCH_FINGERPRINT:
        raise RuntimeError(
            "DUNG: batch fingerprint khong con khop DRY-RUN."
        )

    return preview


def find_existing_batch(service):
    try:
        con = ro_connect()
        try:
            table = str(service.BATCH_TABLE)

            if not table_exists(con, table):
                return None

            row = con.execute(
                f"""
                SELECT *
                FROM {table}
                WHERE school_year_id=?
                  AND level_code=?
                ORDER BY id DESC
                LIMIT 1
                """,
                (YEAR_ID, LEVEL),
            ).fetchone()

            return dict(row) if row is not None else None
        finally:
            con.close()
    except Exception:
        return None


print("=" * 148)
print("THUC HIEN CHINH THUC BATCH THCS - 13 PHUONG AN THUAN")
print("BUOC NAY CO GHI DATABASE THAT")
print("=" * 148)

print()
print("1. HASH GATE TRUOC THUC HIEN")
print("-" * 148)

before_hashes = hash_gate()

print()
print("2. WAL / JOURNAL GATE")
print("-" * 148)

wal_journal_gate()

sys.path.insert(0, str(ROOT))

from app.services import school_merger_level_batch_service as service

print()
print("3. PREFLIGHT CUOI CUNG")
print("-" * 148)

preview = validate_preview(service)

actor = load_actor()

print()
print("4. DOI TUONG THUC HIEN")
print("-" * 148)
print("actor =", actor)
print()
print("13 PLAN DUOC PHEP:")
for i, pid in enumerate(sorted(EXPECTED_PLAN_IDS), start=1):
    print(f"{i:02d}. {pid}")

confirm_phrase = str(
    service.LEVEL_BATCH_CONFIRM_PHRASE
)

print()
print("=" * 148)
print("XAC NHAN GHI THAT")
print("=" * 148)
print("Chi 13 plan tren se nam trong batch THCS thuan.")
print("19 truong hop xu ly rieng KHONG nam trong candidate.")
print("THCS Nghi Huong KHONG bi tac dong.")
print()
print("Nhap YES de tiep tuc.")
scope = input("> ").strip()

if scope.lower() != "yes":
    print()
    print("DA HUY. DATABASE CHUA DUOC GHI.")
    raise SystemExit(0)

print()
print("Nhap CHINH XAC cau xac nhan sau:")
print(confirm_phrase)
phrase = input("> ").strip()

if phrase.upper() != confirm_phrase:
    print()
    print("DA HUY: cau xac nhan khong dung.")
    print("DATABASE CHUA DUOC GHI.")
    raise SystemExit(0)

print()
print("5. REVALIDATE NGAY TRUOC LENH GHI")
print("-" * 148)

hash_gate()
wal_journal_gate()
validate_preview(service)

print()
print("=" * 148)
print("BAT DAU THUC HIEN CHINH THUC")
print("=" * 148)

try:
    result = service.execute_level_batch(
        school_year_id=YEAR_ID,
        level_code=LEVEL,
        actor=actor,
        expected_batch_fingerprint=EXPECTED_BATCH_FINGERPRINT,
        confirmation_scope="yes",
        confirmation_text=phrase,
    )

except Exception as exc:
    print()
    print("=" * 148)
    print("SERVICE BAO LOI")
    print("=" * 148)
    print(type(exc).__name__ + ":", str(exc))

    existing = find_existing_batch(service)

    if existing is not None:
        print()
        print("CANH BAO QUAN TRONG:")
        print("DATABASE DA CO BATCH THCS.")
        print("CO THE COMMIT DA THANH CONG TRUOC KHI PHAT SINH LOI NGOAI TRANSACTION.")
        print("TUYET DOI KHONG CHAY LAI.")
        print(
            json.dumps(
                existing,
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        )
    else:
        print()
        print("Chua phat hien batch THCS trong database.")
        print("VAN KHONG CHAY LAI truoc khi doi chieu ket qua.")

    traceback.print_exc()
    raise SystemExit(2)

print()
print("=" * 148)
print("SERVICE RETURNED SUCCESS")
print("=" * 148)

print(
    json.dumps(
        result,
        ensure_ascii=False,
        indent=2,
        default=str,
    )
)

print()
print("6. HAU KIEM DOC LAI DATABASE")
print("-" * 148)

con = ro_connect()
try:
    integrity = str(
        con.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]
    )

    fk_rows = con.execute(
        "PRAGMA foreign_key_check"
    ).fetchall()

    batch_table = str(service.BATCH_TABLE)

    batch_count = 0
    batch_row = None

    if table_exists(con, batch_table):
        batch_rows = con.execute(
            f"""
            SELECT *
            FROM {batch_table}
            WHERE school_year_id=?
              AND level_code=?
            ORDER BY id
            """,
            (YEAR_ID, LEVEL),
        ).fetchall()

        batch_count = len(batch_rows)

        if batch_rows:
            batch_row = dict(batch_rows[-1])

    official_count = 0

    if table_exists(
        con,
        "school_merger_official_executions",
    ):
        marks = ",".join(
            "?" for _ in EXPECTED_PLAN_IDS
        )

        official_count = int(
            con.execute(
                f"""
                SELECT COUNT(DISTINCT plan_id)
                FROM school_merger_official_executions
                WHERE school_year_id=?
                  AND plan_id IN ({marks})
                """,
                (
                    YEAR_ID,
                    *sorted(EXPECTED_PLAN_IDS),
                ),
            ).fetchone()[0]
            or 0
        )

finally:
    con.close()

print("integrity_check       =", integrity)
print("foreign_key_check     =", len(fk_rows))
print("THCS batch rows       =", batch_count)
print("official 13 plan rows =", official_count)

if batch_row is not None:
    print("batch_id              =", batch_row.get("id"))
    print("backup_name           =", batch_row.get("backup_name"))
    print("executed_count        =", batch_row.get("executed_count"))
    print("done_before_count     =", batch_row.get("done_before_count"))
    print("keep_count            =", batch_row.get("keep_count"))

print()
print("7. TRANG THAI BATCH SAU THUC HIEN")
print("-" * 148)

try:
    post = service.build_level_batch_preview(
        school_year_id=YEAR_ID,
        level_code=LEVEL,
    )

    print("counts             =", post.get("counts"))
    print(
        "candidate_count    =",
        len(post.get("candidates") or []),
    )
    print(
        "previous_batch     =",
        bool(post.get("previous_batch")),
    )
    print(
        "ready_for_execution=",
        post.get("ready_for_execution"),
    )

except Exception as exc:
    print(
        "Khong doc duoc post-preview:",
        type(exc).__name__,
        str(exc),
    )

print()
print("8. CONFIG FILE IMMUTABILITY")
print("-" * 148)

for label in (
    "level_service",
    "engine",
    "roster",
    "resolution",
    "history",
):
    path, expected = EXPECTED_FILES[label]
    current = sha256(path)

    print(
        f"{label:14s}: "
        f"{before_hashes[label]} -> {current}"
    )

print()
print("DB SHA BEFORE =", before_hashes["db"])
print("DB SHA AFTER  =", sha256(DB))

print()
print("=" * 148)

success_checks = (
    int(result.get("executed_count") or 0) == 13
    and int(result.get("keep_count") or 0) == 36
    and int(result.get("done_before_count") or 0) == 84
    and str(result.get("integrity") or "").lower() == "ok"
    and int(result.get("foreign_key_errors") or 0) == 0
    and integrity.lower() == "ok"
    and len(fk_rows) == 0
    and batch_count == 1
    and official_count == 13
)

if success_checks:
    print("THUC HIEN CHINH THUC 13 PHUONG AN THCS: COMMITTED")
    print("HAU KIEM CO BAN: PASS")
else:
    print("BATCH DA DUOC THUC HIEN NHUNG HAU KIEM CO DIEM CAN DOI CHIEU.")
    print("TUYET DOI KHONG CHAY LAI.")

print()
print("TU THOI DIEM NAY: KHONG CHAY LAI SCRIPT SAP NHAP THCS.")
print("GUI TOAN BO KET QUA MAN HINH CHO CHATGPT DE KIEM TOAN CUOI.")
print("=" * 148)
