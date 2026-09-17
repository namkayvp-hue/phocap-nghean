# -*- coding: utf-8 -*-
r"""
V13.5 - NÂNG ENGINE SÁP NHẬP: CURRENT + FUTURE
===============================================

MỤC TIÊU
--------
Khóa đúng quy tắc nghiệp vụ toàn tỉnh:

- Dữ liệu các năm TRƯỚC thời điểm sáp nhập: GIỮ NGUYÊN tại trường nguồn.
- Dữ liệu năm HIỆN HÀNH và mọi năm TƯƠNG LAI: THEO TRƯỜNG ĐÍCH.
- Không dùng school_year_id lớn/nhỏ để suy ra trước/sau.
- Thứ tự năm học được xác định bằng code, ví dụ:
    2025-2026 -> PAST
    2026-2027 -> CURRENT
    2027-2028 -> FUTURE

V13.5 CHỈ SỬA ENGINE
--------------------
- KHÔNG thực hiện sáp nhập.
- KHÔNG sửa dữ liệu nghiệp vụ trong database.
- KHÔNG sửa school_merger_approved_plans.json.
- 412 plan APPROVED giữ nguyên.
- 6 QĐ3805 COMPLETED giữ nguyên.

NÂNG CẤP
--------
1. classes: CURRENT + FUTURE -> target.
2. student_enrollments: CURRENT + FUTURE -> target.
3. staff_year_records: CURRENT + FUTURE -> target.
   Rollover từ năm trước vẫn chỉ tạo hồ sơ còn thiếu cho CURRENT.
4. Tất cả bảng có school_id + school_year_id:
   CURRENT + FUTURE -> target; PAST giữ nguyên.
5. Bảng có school_id nhưng không có school_year_id:
   truy vết năm gián tiếp; CURRENT + FUTURE -> target.
6. Audit/log giữ tại nguồn.
7. Preview hiển thị đúng:
   "Năm hiện hành + tương lai sẽ xử lý".
8. Post-check không cho còn CURRENT/FUTURE tại source.

CÀI ĐẶT
-------
cd C:\PhoCap
.\.venv\Scripts\python.exe .\cai_dat_v13_5_current_future_sap_nhap_toan_tinh.py
"""

from __future__ import annotations

import ast
import hashlib
import json
import py_compile
import shutil
import sqlite3
import sys
import zipfile
from datetime import datetime
from pathlib import Path
import base64
import zlib


ROOT = Path(r"C:\PhoCap")
SERVICE = ROOT / "app" / "services" / "school_merger_service.py"
TEMPLATE = ROOT / "app" / "templates" / "data_tools" / "school_merger.html"
DB_PATH = ROOT / "data" / "phocap.db"
PLAN_FILE = ROOT / "data" / "school_merger_approved_plans.json"
EXPORTS = ROOT / "exports"

EXPECTED_OLD_SERVICE_SHA = "4879c385499e5c47eea7b1b0d3f9772cd881de6abe26097e7f9ff05374c7762a"
NEW_SERVICE_SHA = "41aa2d3cd305451c04f79fdc28e719142ffcc5fcc0c1893232f4a762f04e7764"
NEW_SERVICE_ZLIB_B64 = """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"""

MARKER = "# === V13_5_CURRENT_FUTURE_SCOPE ==="


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def db_health() -> tuple[str, int]:
    con = sqlite3.connect(str(DB_PATH))
    try:
        integrity = str(
            con.execute("PRAGMA integrity_check").fetchone()[0]
        )
        fk = len(
            con.execute("PRAGMA foreign_key_check").fetchall()
        )
        return integrity, fk
    finally:
        con.close()


def load_plans() -> list[dict]:
    payload = json.loads(
        PLAN_FILE.read_text(encoding="utf-8")
    )
    plans = payload.get("plans")
    if not isinstance(plans, list):
        raise RuntimeError("Plan JSON không có mảng plans.")
    return [p for p in plans if isinstance(p, dict)]


def validate_plan_registry(plans: list[dict]) -> tuple[int, int]:
    qd = [
        p for p in plans
        if (
            str(p.get("id") or "").startswith("QD3805-")
            or "3805" in str(p.get("document_code") or "")
        )
    ]
    if len(qd) != 6:
        raise RuntimeError(
            f"QĐ3805 phải còn đúng 6 plan; hiện={len(qd)}."
        )
    bad_qd = [
        str(p.get("id") or "")
        for p in qd
        if str(p.get("status") or "").upper() != "COMPLETED"
    ]
    if bad_qd:
        raise RuntimeError(
            "QĐ3805 chưa COMPLETED: " + ", ".join(bad_qd)
        )

    batch = [
        p for p in plans
        if (
            str(p.get("document_code") or "")
            == "NGUON-SAP-NHAP-TOAN-TINH"
            and int(p.get("school_year_id") or 0) == 2
        )
    ]
    approved = [
        p for p in batch
        if str(p.get("status") or "").upper() == "APPROVED"
    ]

    if len(batch) != 412 or len(approved) != 412:
        raise RuntimeError(
            f"Phải có đúng 412 plan toàn tỉnh APPROVED; "
            f"batch={len(batch)}, approved={len(approved)}."
        )

    return len(qd), len(approved)


def year_scope_report() -> tuple[str, list[int], list[int], dict[int, str]]:
    con = sqlite3.connect(str(DB_PATH))
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            "SELECT id,code,name FROM school_years ORDER BY id"
        ).fetchall()
    finally:
        con.close()

    import re

    starts = {}
    labels = {}
    for row in rows:
        text = str(row["code"] or row["name"] or "")
        m = re.search(r"(\d{4})\D+(\d{4})", text)
        if not m:
            raise RuntimeError(
                f"Không phân loại được năm học id={row['id']}: {text!r}"
            )
        starts[int(row["id"])] = int(m.group(1))
        labels[int(row["id"])] = text

    if 2 not in starts or labels[2] != "2026-2027":
        raise RuntimeError(
            f"school_year_id=2 không còn là 2026-2027: {labels.get(2)}"
        )

    selected_start = starts[2]
    move_ids = sorted(
        yid for yid, start in starts.items()
        if start >= selected_start
    )
    past_ids = sorted(
        yid for yid, start in starts.items()
        if start < selected_start
    )

    return labels[2], move_ids, past_ids, labels


def scan_future_rows(plans: list[dict], move_ids: list[int]) -> list[dict]:
    future_ids = [x for x in move_ids if x != 2]
    if not future_ids:
        return []

    source_ids = sorted({
        int(sid)
        for p in plans
        if str(p.get("document_code") or "")
           == "NGUON-SAP-NHAP-TOAN-TINH"
        for sid in (p.get("source_school_ids") or [])
    })
    if not source_ids:
        return []

    con = sqlite3.connect(str(DB_PATH))
    con.row_factory = sqlite3.Row
    try:
        tables = [
            str(r[0])
            for r in con.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        ]

        result = []
        for table in tables:
            cols = {
                str(r[1])
                for r in con.execute(
                    f'PRAGMA table_info("{table}")'
                ).fetchall()
            }
            if not {"school_id", "school_year_id"} <= cols:
                continue

            sql = (
                f'SELECT school_year_id,COUNT(*) AS n '
                f'FROM "{table}" '
                f'WHERE school_id IN ({",".join("?" for _ in source_ids)}) '
                f'AND school_year_id IN ({",".join("?" for _ in future_ids)}) '
                f'GROUP BY school_year_id'
            )
            rows = con.execute(
                sql,
                [*source_ids, *future_ids],
            ).fetchall()
            for row in rows:
                result.append({
                    "table": table,
                    "school_year_id": int(row["school_year_id"]),
                    "rows": int(row["n"]),
                })
        return result
    finally:
        con.close()


def main() -> int:
    print("=" * 126)
    print("V13.5 - CURRENT + FUTURE CHO SÁP NHẬP TOÀN TỈNH")
    print("=" * 126)
    print("Database nghiệp vụ: KHÔNG THAY ĐỔI")
    print("Plan JSON: KHÔNG THAY ĐỔI")

    for path in (SERVICE, TEMPLATE, DB_PATH, PLAN_FILE):
        if not path.exists():
            raise RuntimeError(f"Không tìm thấy: {path}")

    integrity_before, fk_before = db_health()
    if integrity_before.lower() != "ok" or fk_before != 0:
        raise RuntimeError(
            f"DB preflight lỗi: integrity={integrity_before}, FK={fk_before}"
        )

    plans = load_plans()
    qd_count, approved_count = validate_plan_registry(plans)

    old_hash = sha(SERVICE)
    service_text = SERVICE.read_text(encoding="utf-8-sig")

    if MARKER in service_text:
        if old_hash != NEW_SERVICE_SHA:
            raise RuntimeError(
                "Service có marker V13.5 nhưng SHA không đúng bản chuẩn; dừng."
            )
        already = True
    else:
        if old_hash != EXPECTED_OLD_SERVICE_SHA:
            raise RuntimeError(
                "school_merger_service.py không đúng nền V13 đã khóa.\n"
                f"SHA hiện tại={old_hash}\n"
                f"SHA cần={EXPECTED_OLD_SERVICE_SHA}"
            )
        already = False

    year_code, move_ids, past_ids, labels = year_scope_report()
    future_before = scan_future_rows(plans, move_ids)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = EXPORTS / f"backup_source_v13_5_current_future_{stamp}"
    backup.mkdir(parents=True, exist_ok=False)

    for path in (SERVICE, TEMPLATE):
        dst = backup / path.relative_to(ROOT)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dst)

    try:
        if not already:
            new_service = zlib.decompress(
                base64.b64decode(
                    NEW_SERVICE_ZLIB_B64.encode("ascii")
                )
            )
            if hashlib.sha256(new_service).hexdigest() != NEW_SERVICE_SHA:
                raise RuntimeError("Payload service V13.5 sai SHA256.")

            SERVICE.write_bytes(new_service)

        template_text = TEMPLATE.read_text(
            encoding="utf-8-sig"
        )
        old_header = "Năm hiện hành sẽ xử lý"
        new_header = "Năm hiện hành + tương lai sẽ xử lý"
        if new_header not in template_text:
            if old_header not in template_text:
                raise RuntimeError(
                    "Không tìm thấy tiêu đề dữ liệu năm trong template."
                )
            template_text = template_text.replace(
                old_header,
                new_header,
                1,
            )
            TEMPLATE.write_text(
                template_text,
                encoding="utf-8",
            )

        # Cú pháp Python.
        final_service = SERVICE.read_text(encoding="utf-8")
        ast.parse(final_service)
        py_compile.compile(str(SERVICE), doraise=True)

        required = [
            MARKER,
            "def _year_scope_ids(",
            "MOVE_CLASSES_CURRENT_FUTURE",
            "MOVE_ENROLLMENTS_CURRENT_FUTURE",
            "MOVE_CURRENT_FUTURE_AND_ROLLOVER_STAFF",
            "MOVE_CURRENT_FUTURE_BY_INDIRECT_TRACE",
            "year_ids=move_year_ids",
            "CURRENT/FUTURE",
        ]
        missing = [x for x in required if x not in final_service]
        if missing:
            raise RuntimeError(
                "Service V13.5 thiếu marker: " + repr(missing)
            )

        # Jinja parse.
        from jinja2 import Environment
        Environment().parse(
            TEMPLATE.read_text(encoding="utf-8")
        )

        if sha(SERVICE) != NEW_SERVICE_SHA:
            raise RuntimeError("SHA service sau V13.5 không đúng.")

        integrity_after, fk_after = db_health()
        if integrity_after.lower() != "ok" or fk_after != 0:
            raise RuntimeError(
                f"DB hậu kiểm lỗi: integrity={integrity_after}, FK={fk_after}"
            )

        # Xác nhận DB/plan registry vẫn như trước.
        plans_after = load_plans()
        qd_after, approved_after = validate_plan_registry(
            plans_after
        )

        report = backup / "00_KET_QUA_V13_5.txt"
        report.write_text(
            "\n".join([
                "V13.5 - CURRENT + FUTURE",
                "=" * 90,
                "STATUS=SUCCESS",
                "Database nghiệp vụ=KHÔNG THAY ĐỔI",
                "Plan JSON=KHÔNG THAY ĐỔI",
                f"Năm sáp nhập={year_code} / id=2",
                f"PAST year ids={past_ids}",
                f"CURRENT+FUTURE year ids={move_ids}",
                f"QĐ3805 COMPLETED={qd_after}",
                f"Plan toàn tỉnh APPROVED={approved_after}",
                f"Future rows phát hiện tại 412 source trước chạy={sum(x['rows'] for x in future_before)}",
                f"Future detail={future_before}",
                f"DB integrity={integrity_after}",
                f"DB FK={fk_after}",
                f"Backup source={backup}",
            ]),
            encoding="utf-8",
        )

        zip_path = ROOT / f"ket_qua_cai_v13_5_current_future_{stamp}.zip"
        with zipfile.ZipFile(
            zip_path,
            "w",
            compression=zipfile.ZIP_DEFLATED,
        ) as zf:
            zf.write(report, arcname=report.name)

        print()
        print("=" * 126)
        print("CÀI V13.5 THÀNH CÔNG")
        print("=" * 126)
        print(f"Năm sáp nhập: {year_code} (id=2)")
        print(f"PAST year ids: {past_ids}")
        print(f"CURRENT + FUTURE year ids: {move_ids}")
        print(
            "Future rows tại 412 source trước sáp nhập: "
            f"{sum(x['rows'] for x in future_before)}"
        )
        for item in future_before:
            print(
                f"  {item['table']} | year_id={item['school_year_id']} "
                f"| rows={item['rows']}"
            )
        print(f"QĐ3805 COMPLETED: {qd_after}")
        print(f"Plan toàn tỉnh APPROVED: {approved_after}")
        print("Database nghiệp vụ: KHÔNG THAY ĐỔI")
        print("Plan JSON: KHÔNG THAY ĐỔI")
        print(f"DB integrity: {integrity_after}")
        print(f"DB FK errors: {fk_after}")
        print(f"Backup source: {backup}")
        print(f"ZIP kết quả: {zip_path}")
        return 0

    except Exception:
        for path in (SERVICE, TEMPLATE):
            src = backup / path.relative_to(ROOT)
            if src.exists():
                path.parent.mkdir(
                    parents=True,
                    exist_ok=True,
                )
                shutil.copy2(src, path)
        raise


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print()
        print("=" * 126)
        print("V13.5 DỪNG AN TOÀN - ĐÃ KHÔI PHỤC SOURCE")
        print("=" * 126)
        print(repr(exc))
        print("Database nghiệp vụ: KHÔNG THAY ĐỔI")
        print("Plan JSON: KHÔNG THAY ĐỔI")
        raise SystemExit(2)
