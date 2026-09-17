# -*- coding: utf-8 -*-
r"""
V13.5.1 - ĐÓNG GÓI ENGINE SÁP NHẬP HIỆN TẠI
=============================================

MỤC ĐÍCH
--------
Lấy đúng mã nguồn sáp nhập đang chạy trên máy để vá V13.5 theo bản thực tế.

CHỈ ĐỌC:
- Không sửa database.
- Không sửa mã nguồn.
- Không sửa plan JSON.
- Không thực hiện sáp nhập.

ZIP gồm:
- app/services/school_merger_service.py
- app/routers/school_merger.py
- app/templates/data_tools/school_merger.html
- app/templates/data_tools/school_merger_plans.html
- data/school_merger_approved_plans.json
- 00_SHA256.txt
- 01_DB_SCHEMA_SCHOOL_SCOPE.txt
- 02_SCHOOL_YEARS.txt
- 03_PLAN_COUNTS.txt
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import sys
import zipfile
from datetime import datetime
from pathlib import Path


ROOT = Path(r"C:\PhoCap")
DB_PATH = ROOT / "data" / "phocap.db"

FILES = [
    ROOT / "app" / "services" / "school_merger_service.py",
    ROOT / "app" / "routers" / "school_merger.py",
    ROOT / "app" / "templates" / "data_tools" / "school_merger.html",
    ROOT / "app" / "templates" / "data_tools" / "school_merger_plans.html",
    ROOT / "data" / "school_merger_approved_plans.json",
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def qident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def main() -> int:
    print("=" * 118)
    print("V13.5.1 - ĐÓNG GÓI ENGINE SÁP NHẬP HIỆN TẠI")
    print("=" * 118)
    print("CHỈ ĐỌC - KHÔNG SỬA DB / SOURCE / PLAN")

    missing = [str(p) for p in [DB_PATH, *FILES] if not p.exists()]
    if missing:
        print("Thiếu tệp:")
        for p in missing:
            print(" -", p)
        return 2

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    work = ROOT / f"nguon_v13_5_1_engine_sap_nhap_{stamp}"
    zip_path = ROOT / f"nguon_v13_5_1_engine_sap_nhap_{stamp}.zip"
    work.mkdir(parents=True, exist_ok=False)

    # Copy source files preserving relative paths.
    for src in FILES:
        dst = work / src.relative_to(ROOT)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    # SHA report.
    sha_lines = [
        "V13.5.1 - SHA256 ENGINE HIỆN TẠI",
        "=" * 90,
        "",
    ]
    for src in FILES:
        sha_lines.append(
            f"{sha256(src)}  {src.relative_to(ROOT)}"
        )
    (work / "00_SHA256.txt").write_text(
        "\n".join(sha_lines),
        encoding="utf-8",
    )

    con = sqlite3.connect(
        f"file:{DB_PATH.as_posix()}?mode=ro",
        uri=True,
        timeout=30,
    )
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only=ON")

    try:
        integrity = str(
            con.execute("PRAGMA integrity_check").fetchone()[0]
        )
        fk = con.execute("PRAGMA foreign_key_check").fetchall()

        schema_lines = [
            "V13.5.1 - DB SCHEMA LIÊN QUAN SCHOOL/YEAR",
            "=" * 100,
            f"integrity_check={integrity}",
            f"foreign_key_errors={len(fk)}",
            "",
        ]

        tables = [
            str(r["name"])
            for r in con.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type='table'
                  AND name NOT LIKE 'sqlite_%'
                ORDER BY name
                """
            ).fetchall()
        ]

        for table in tables:
            cols = con.execute(
                f"PRAGMA table_info({qident(table)})"
            ).fetchall()
            names = {str(r["name"]) for r in cols}

            if (
                "school_id" not in names
                and "school_year_id" not in names
            ):
                continue

            schema_lines.append(f"[{table}]")
            schema_lines.append(
                "columns="
                + ", ".join(
                    f"{r['name']}:{r['type']}"
                    for r in cols
                )
            )

            fks = con.execute(
                f"PRAGMA foreign_key_list({qident(table)})"
            ).fetchall()
            if fks:
                schema_lines.append(
                    "foreign_keys="
                    + " | ".join(
                        f"{r['from']}->{r['table']}.{r['to']}"
                        for r in fks
                    )
                )
            schema_lines.append("")

        (work / "01_DB_SCHEMA_SCHOOL_SCOPE.txt").write_text(
            "\n".join(schema_lines),
            encoding="utf-8",
        )

        year_rows = con.execute(
            """
            SELECT id,code,name,start_date,end_date,is_active
            FROM school_years
            ORDER BY id
            """
        ).fetchall()

        year_lines = [
            "V13.5.1 - SCHOOL YEARS",
            "=" * 90,
        ]
        for r in year_rows:
            year_lines.append(
                f"id={r['id']} | code={r['code']} | "
                f"name={r['name']} | start={r['start_date']} | "
                f"end={r['end_date']} | is_active={r['is_active']}"
            )

        (work / "02_SCHOOL_YEARS.txt").write_text(
            "\n".join(year_lines),
            encoding="utf-8",
        )

    finally:
        con.close()

    # Plan counts only.
    payload = json.loads(
        (ROOT / "data" / "school_merger_approved_plans.json")
        .read_text(encoding="utf-8")
    )
    plans = [
        p for p in payload.get("plans") or []
        if isinstance(p, dict)
    ]

    counts = {}
    qd3805 = []
    for p in plans:
        status = str(p.get("status") or "").upper()
        counts[status] = counts.get(status, 0) + 1

        if (
            str(p.get("id") or "").startswith("QD3805-")
            or "3805" in str(p.get("document_code") or "")
        ):
            qd3805.append(p)

    plan_lines = [
        "V13.5.1 - PLAN COUNTS",
        "=" * 90,
        f"total_plans={len(plans)}",
        f"status_counts={counts}",
        f"qd3805_count={len(qd3805)}",
        "qd3805_statuses="
        + repr([
            (
                p.get("id"),
                p.get("status"),
                p.get("school_year_id"),
            )
            for p in qd3805
        ]),
    ]
    (work / "03_PLAN_COUNTS.txt").write_text(
        "\n".join(plan_lines),
        encoding="utf-8",
    )

    with zipfile.ZipFile(
        zip_path,
        "w",
        compression=zipfile.ZIP_DEFLATED,
    ) as zf:
        for p in sorted(work.rglob("*")):
            if p.is_file():
                zf.write(
                    p,
                    arcname=str(p.relative_to(work)),
                )

    print()
    print("=" * 118)
    print("ĐÓNG GÓI V13.5.1 THÀNH CÔNG")
    print("=" * 118)
    print(
        "school_merger_service.py SHA256:",
        sha256(
            ROOT
            / "app"
            / "services"
            / "school_merger_service.py"
        ),
    )
    print("Database: KHÔNG THAY ĐỔI")
    print("Source: KHÔNG THAY ĐỔI")
    print("Plan JSON: KHÔNG THAY ĐỔI")
    print(f"ZIP: {zip_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
