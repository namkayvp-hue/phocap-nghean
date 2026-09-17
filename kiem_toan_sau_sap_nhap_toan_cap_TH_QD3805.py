# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(r"C:\PhoCap")
DB = ROOT / "data" / "phocap.db"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.school_merger_level_batch_service import build_level_batch_preview  # noqa: E402


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def ro_connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB.resolve().as_uri() + "?mode=ro", uri=True, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only=ON")
    con.execute("PRAGMA foreign_keys=ON")
    return con


def table_exists(con: sqlite3.Connection, name: str) -> bool:
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (name,),
    ).fetchone() is not None


def year_id(con: sqlite3.Connection, code: str) -> int:
    row = con.execute(
        "SELECT id FROM school_years "
        "WHERE REPLACE(REPLACE(code,'–','-'),'—','-')=? LIMIT 1",
        (code,),
    ).fetchone()
    if row is None:
        raise RuntimeError(f"Không tìm thấy năm học {code}.")
    return int(row["id"])


def main() -> None:
    print("=" * 118)
    print("KIỂM TOÁN SAU SÁP NHẬP TOÀN CẤP - TIỂU HỌC - QĐ3805")
    print("Chế độ: CHỈ ĐỌC - KHÔNG GHI DATABASE")
    print("Database:", DB)
    print("=" * 118)

    before = sha256_file(DB)

    with ro_connect() as con:
        yid = year_id(con, "2026-2027")
        integrity = str(con.execute("PRAGMA integrity_check").fetchone()[0])
        fk = con.execute("PRAGMA foreign_key_check").fetchall()

        if not table_exists(con, "school_merger_level_batches"):
            raise RuntimeError("Không tìm thấy bảng school_merger_level_batches.")

        batches = con.execute(
            "SELECT * FROM school_merger_level_batches "
            "WHERE school_year_id=? AND level_code='TH' ORDER BY id",
            (yid,),
        ).fetchall()

        print(f"Số batch TH 2026-2027: {len(batches)}")
        if not batches:
            raise RuntimeError("Chưa có batch Tiểu học đã commit.")

        batch = dict(batches[-1])
        try:
            summary = json.loads(str(batch.get("summary_json") or "{}"))
        except Exception:
            summary = {}

        print("Batch ID:", batch.get("id"))
        print("Giữ nguyên:", batch.get("keep_count"))
        print("Đã thực hiện trước:", batch.get("done_before_count"))
        print("Thực hiện trong đợt:", batch.get("executed_count"))
        print("Backup:", batch.get("backup_name"))
        print("Integrity lưu trong batch:", summary.get("integrity"))
        print("FK errors lưu trong batch:", summary.get("foreign_key_errors"))

        operation_ids = [
            int(x.get("operation_id"))
            for x in (summary.get("operations") or [])
            if x.get("operation_id") is not None
        ]
        print("Operation IDs trong batch:", len(operation_ids))

        official_count = 0
        if operation_ids and table_exists(con, "school_merger_official_executions"):
            placeholders = ",".join("?" for _ in operation_ids)
            official_count = int(con.execute(
                f"SELECT COUNT(*) FROM school_merger_official_executions "
                f"WHERE operation_id IN ({placeholders})",
                tuple(operation_ids),
            ).fetchone()[0])
        print("Official execution rows tương ứng:", official_count)

        source_ids = []
        target_ids = []
        if operation_ids and table_exists(con, "school_merger_operations"):
            placeholders = ",".join("?" for _ in operation_ids)
            op_rows = [
                dict(r) for r in con.execute(
                    f"SELECT id,target_school_id,source_school_ids_json "
                    f"FROM school_merger_operations WHERE id IN ({placeholders}) ORDER BY id",
                    tuple(operation_ids),
                ).fetchall()
            ]
            for r in op_rows:
                try:
                    ids = json.loads(str(r.get("source_school_ids_json") or "[]"))
                except Exception:
                    ids = []
                for sid in ids:
                    try:
                        sid = int(sid)
                    except Exception:
                        continue
                    if sid not in source_ids:
                        source_ids.append(sid)
                try:
                    tid = int(r.get("target_school_id"))
                    if tid not in target_ids:
                        target_ids.append(tid)
                except Exception:
                    pass

        print("Số trường nguồn duy nhất trong 19 operation:", len(source_ids))
        print("Số trường đích duy nhất trong 19 operation:", len(target_ids))

        source_active = []
        if source_ids:
            placeholders = ",".join("?" for _ in source_ids)
            source_active = [
                dict(r) for r in con.execute(
                    f"SELECT id,code,name,is_active FROM schools "
                    f"WHERE id IN ({placeholders}) AND COALESCE(is_active,1)<>0 ORDER BY name",
                    tuple(source_ids),
                ).fetchall()
            ]
        print("Nguồn còn active:", len(source_active))

        target_inactive = []
        if target_ids:
            placeholders = ",".join("?" for _ in target_ids)
            target_inactive = [
                dict(r) for r in con.execute(
                    f"SELECT id,code,name,is_active FROM schools "
                    f"WHERE id IN ({placeholders}) AND COALESCE(is_active,1)=0 ORDER BY name",
                    tuple(target_ids),
                ).fetchall()
            ]
        print("Đích bị inactive:", len(target_inactive))

        residual_staff = 0
        if source_ids and table_exists(con, "staff_year_records"):
            placeholders = ",".join("?" for _ in source_ids)
            residual_staff = int(con.execute(
                f"SELECT COUNT(*) FROM staff_year_records "
                f"WHERE school_year_id=? AND school_id IN ({placeholders}) "
                f"AND COALESCE(is_active,1)=1",
                (yid, *source_ids),
            ).fetchone()[0])
        print("Nhân sự active 2026-2027 còn tại nguồn:", residual_staff)

    preview = build_level_batch_preview(
        school_year_id=yid,
        level_code="TH",
    )
    counts = preview.get("counts") or {}

    print("-" * 118)
    print(
        "Preview cuối: "
        f"DONE={counts.get('DONE')} | READY={counts.get('READY')} | "
        f"BLOCK={counts.get('BLOCK')} | KEEP={counts.get('KEEP')}"
    )
    print("Previous batch:", bool(preview.get("previous_batch")))
    print("All done:", bool(preview.get("all_done")))
    print("Effective block:", preview.get("effective_block_count"))
    print("-" * 118)

    after = sha256_file(DB)
    unchanged = before == after

    checks = {
        "integrity_ok": integrity.lower() == "ok",
        "foreign_key_errors_zero": len(fk) == 0,
        "one_batch_only": len(batches) == 1,
        "done_before_141": int(batch.get("done_before_count") or 0) == 141,
        "executed_19": int(batch.get("executed_count") or 0) == 19,
        "keep_67": int(batch.get("keep_count") or 0) == 67,
        "official_execution_19": official_count == 19,
        "source_active_zero": len(source_active) == 0,
        "target_inactive_zero": len(target_inactive) == 0,
        "source_staff_residual_zero": residual_staff == 0,
        "preview_done_160": int(counts.get("DONE") or 0) == 160,
        "preview_ready_zero": int(counts.get("READY") or 0) == 0,
        "preview_block_zero": int(counts.get("BLOCK") or 0) == 0,
        "previous_batch_true": bool(preview.get("previous_batch")),
        "database_unchanged_by_audit": unchanged,
    }

    failed = [k for k, v in checks.items() if not v]

    print("KẾT LUẬN:")
    for k, v in checks.items():
        print(f"  {'PASS' if v else 'FAIL'} - {k}")

    print("-" * 118)
    print("Database sau kiểm toán:", "KHÔNG THAY ĐỔI" if unchanged else "CẢNH BÁO HASH THAY ĐỔI")
    if failed:
        print("KẾT QUẢ CHUNG: CHƯA ĐẠT")
        print("Các mục chưa đạt:", ", ".join(failed))
        raise SystemExit(2)

    print("KẾT QUẢ CHUNG: PASS - TIỂU HỌC ĐÃ ĐÓNG SÁP NHẬP TOÀN CẤP AN TOÀN")
    print("=" * 118)


if __name__ == "__main__":
    main()
