# -*- coding: utf-8 -*-
r"""
V12 - ĐÓNG GÓI ĐÚNG NGUỒN CẦN THIẾT
CHO CHỨC NĂNG "NẠP HỌC SINH ĐỐI CHIẾU THEO XÃ/PHƯỜNG"
================================================================

MỤC TIÊU
--------
Tạo một ZIP nhỏ chứa đúng mã nguồn/schema cần để xây bộ cài chính thức V12.

KHÔNG:
- sửa database;
- sửa mã nguồn;
- đưa database thật vào ZIP;
- đưa dữ liệu học sinh cá nhân vào ZIP;
- đưa .venv/backups/cache vào ZIP.

ZIP gồm:
1. Các file lõi:
   - app/main.py
   - app/database.py
   - router đối chiếu học sinh
   - router học sinh hiện có
   - access control/auth liên quan
   - school merger service + QĐ3805 plan
2. Model files có Student / StudentEnrollment / Class / School / SchoolYear / Commune.
3. Template có student/comparison + base/layout/index.
4. SQLite schema (CREATE TABLE/INDEX/TRIGGER) KHÔNG CÓ DỮ LIỆU.
5. Metadata an toàn:
   - school_years
   - communes
   - schools chỉ: id/code/name/commune_id/level/is_active
   - row counts các bảng liên quan.
6. Route map và danh sách file.

CHẠY
----
    cd C:\PhoCap
    .\.venv\Scripts\python.exe .\dong_goi_nguon_v12_nap_hoc_sinh_doi_chieu_theo_xa.py

KẾT QUẢ
-------
    C:\PhoCap\nguon_v12_nap_hoc_sinh_doi_chieu_theo_xa_<timestamp>.zip
"""

from __future__ import annotations

import ast
import csv
import json
import os
import re
import sqlite3
import sys
import zipfile
from datetime import datetime
from pathlib import Path


ROOT = Path(r"C:\PhoCap")
APP = ROOT / "app"
DB = ROOT / "data" / "phocap.db"
PLAN = ROOT / "data" / "school_merger_approved_plans.json"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
WORK = ROOT / f"_nguon_v12_collect_{STAMP}"
ZIP_OUT = ROOT / f"nguon_v12_nap_hoc_sinh_doi_chieu_theo_xa_{STAMP}.zip"

SKIP_DIRS = {
    ".venv", "venv", "__pycache__", ".git", ".idea",
    ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "node_modules", "backups", "exports",
}

CORE_RELATIVE = [
    "app/main.py",
    "app/database.py",
    "app/routers/student_survey_comparison.py",
    "app/routers/students.py",
    "app/routers/student_management.py",
    "app/services/school_merger_service.py",
    "app/middleware/access_control.py",
    "app/access_control.py",
    "data/school_merger_approved_plans.json",
]

MODEL_CLASS_TOKENS = (
    "class Student(",
    "class StudentEnrollment(",
    "class SchoolClass(",
    "class Class(",
    "class School(",
    "class SchoolYear(",
    "class Commune(",
)

PY_KEYWORDS = (
    "StudentEnrollment",
    "student_survey_comparison",
    "doi-chieu-hoc-sinh",
    "doi_chieu_hoc_sinh",
    "import_students",
    "nhap_hoc_sinh",
)

TPL_KEYWORDS = (
    "student",
    "hoc_sinh",
    "doi_chieu",
    "comparison",
)

SAFE_SCHOOL_COLUMNS = (
    "id", "code", "name", "commune_id",
    "level", "education_level", "school_level",
    "is_active",
)

SAFE_COMMUNE_COLUMNS = (
    "id", "code", "name", "is_active",
)

SAFE_YEAR_COLUMNS = (
    "id", "code", "name", "start_year", "end_year",
    "is_active", "is_current",
)


def qident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def copy_file(src: Path, rel: Path, manifest: list[dict]) -> None:
    if not src.exists() or not src.is_file():
        return
    dst = WORK / rel
    ensure_parent(dst)
    dst.write_bytes(src.read_bytes())
    manifest.append({
        "path": str(rel).replace("\\", "/"),
        "size": src.stat().st_size,
    })


def text_safe(path: Path) -> str:
    for enc in ("utf-8", "utf-8-sig", "cp1258"):
        try:
            return path.read_text(encoding=enc)
        except Exception:
            pass
    return ""


def collect_source_files() -> list[dict]:
    manifest: list[dict] = []
    seen: set[Path] = set()

    def add(path: Path) -> None:
        try:
            rel = path.relative_to(ROOT)
        except ValueError:
            return
        if rel in seen:
            return
        seen.add(rel)
        copy_file(path, rel, manifest)

    # Core exact files.
    for rel_text in CORE_RELATIVE:
        add(ROOT / rel_text)

    # Python files: models / student comparison / auth helpers / route registration context.
    if APP.exists():
        for path in APP.rglob("*.py"):
            if any(part in SKIP_DIRS for part in path.parts):
                continue

            txt = text_safe(path)
            name = path.name.lower()
            rel_lower = str(path.relative_to(ROOT)).lower()

            if any(tok in txt for tok in MODEL_CLASS_TOKENS):
                add(path)
                continue

            if any(tok.lower() in txt.lower() for tok in PY_KEYWORDS):
                add(path)
                continue

            if (
                "auth" in name
                or "access" in name
                or "permission" in name
                or "dependencies" in name
            ):
                # Chỉ lấy các helper phân quyền trong app, thường nhỏ.
                add(path)
                continue

            if rel_lower in {
                "app/main.py",
                "app/database.py",
            }:
                add(path)

    # Templates:
    template_root = APP / "templates"
    if template_root.exists():
        for path in template_root.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() not in {".html", ".jinja", ".jinja2"}:
                continue

            rel = path.relative_to(template_root)
            low = str(rel).lower()
            name = path.name.lower()

            if (
                any(k in low for k in TPL_KEYWORDS)
                or name in {
                    "base.html",
                    "layout.html",
                    "index.html",
                    "dashboard.html",
                }
                or "partials" in low
                or "components" in low
            ):
                add(path)

    return manifest


def table_exists(con: sqlite3.Connection, table: str) -> bool:
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone() is not None


def columns(con: sqlite3.Connection, table: str) -> list[str]:
    if not table_exists(con, table):
        return []
    return [
        str(r[1])
        for r in con.execute(
            f"PRAGMA table_info({qident(table)})"
        ).fetchall()
    ]


def write_csv(path: Path, headers: list[str], rows: list[dict]) -> None:
    ensure_parent(path)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def export_safe_table(
    con: sqlite3.Connection,
    table: str,
    preferred_columns: tuple[str, ...],
    out_name: str,
) -> None:
    cols = columns(con, table)
    use = [c for c in preferred_columns if c in cols]
    if not use:
        return

    rows = con.execute(
        "SELECT "
        + ",".join(qident(c) for c in use)
        + f" FROM {qident(table)} ORDER BY "
        + (qident("id") if "id" in use else qident(use[0]))
    ).fetchall()

    data = [
        {c: r[c] for c in use}
        for r in rows
    ]
    write_csv(WORK / "_schema" / out_name, use, data)


def export_schema_and_metadata() -> dict:
    if not DB.exists():
        raise RuntimeError(f"Không tìm thấy database: {DB}")

    con = sqlite3.connect(str(DB))
    con.row_factory = sqlite3.Row

    try:
        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
        fk_errors = con.execute("PRAGMA foreign_key_check").fetchall()

        if integrity != "ok":
            raise RuntimeError(
                f"Database integrity_check không đạt: {integrity}"
            )
        if fk_errors:
            raise RuntimeError(
                f"Database có {len(fk_errors)} lỗi foreign key."
            )

        # Full schema only, no data.
        schema_rows = con.execute(
            """
            SELECT type,name,tbl_name,sql
            FROM sqlite_master
            WHERE type IN ('table','index','trigger','view')
              AND name NOT LIKE 'sqlite_%'
            ORDER BY type,name
            """
        ).fetchall()

        schema_sql = []
        schema_catalog = []

        for r in schema_rows:
            schema_catalog.append({
                "type": r["type"],
                "name": r["name"],
                "table": r["tbl_name"],
                "sql": r["sql"] or "",
            })
            if r["sql"]:
                schema_sql.append(str(r["sql"]).rstrip(";") + ";\n")

        schema_dir = WORK / "_schema"
        schema_dir.mkdir(parents=True, exist_ok=True)

        (schema_dir / "database_schema.sql").write_text(
            "\n".join(schema_sql),
            encoding="utf-8",
        )

        write_csv(
            schema_dir / "schema_catalog.csv",
            ["type", "name", "table", "sql"],
            schema_catalog,
        )

        # Counts only, no PII.
        count_rows = []
        table_names = [
            str(r[0])
            for r in con.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type='table' AND name NOT LIKE 'sqlite_%'
                ORDER BY name
                """
            ).fetchall()
        ]

        for table in table_names:
            try:
                n = con.execute(
                    f"SELECT COUNT(*) FROM {qident(table)}"
                ).fetchone()[0]
            except Exception:
                n = "ERROR"

            relevant = any(
                token in table.lower()
                for token in (
                    "student", "class", "school", "commune",
                    "survey", "import", "historical", "merger",
                )
            )
            if relevant:
                count_rows.append({
                    "table": table,
                    "rows": n,
                    "columns": ",".join(columns(con, table)),
                })

        write_csv(
            schema_dir / "relevant_table_counts.csv",
            ["table", "rows", "columns"],
            count_rows,
        )

        export_safe_table(
            con,
            "school_years",
            SAFE_YEAR_COLUMNS,
            "school_years_safe.csv",
        )
        export_safe_table(
            con,
            "communes",
            SAFE_COMMUNE_COLUMNS,
            "communes_safe.csv",
        )
        export_safe_table(
            con,
            "schools",
            SAFE_SCHOOL_COLUMNS,
            "schools_safe.csv",
        )

        # Index/FK detail for key tables.
        key_tables = [
            "students",
            "student_enrollments",
            "classes",
            "schools",
            "school_years",
            "communes",
            "survey_person_year_records",
            "survey_batches",
        ]
        pragma_rows = []

        for table in key_tables:
            if not table_exists(con, table):
                continue

            for r in con.execute(
                f"PRAGMA table_info({qident(table)})"
            ).fetchall():
                pragma_rows.append({
                    "table": table,
                    "kind": "COLUMN",
                    "name": r[1],
                    "detail": json.dumps({
                        "type": r[2],
                        "notnull": r[3],
                        "default": r[4],
                        "pk": r[5],
                    }, ensure_ascii=False),
                })

            for r in con.execute(
                f"PRAGMA foreign_key_list({qident(table)})"
            ).fetchall():
                pragma_rows.append({
                    "table": table,
                    "kind": "FK",
                    "name": r[3],
                    "detail": json.dumps({
                        "ref_table": r[2],
                        "to": r[4],
                        "on_update": r[5],
                        "on_delete": r[6],
                    }, ensure_ascii=False),
                })

            for r in con.execute(
                f"PRAGMA index_list({qident(table)})"
            ).fetchall():
                idx_name = str(r[1])
                idx_cols = [
                    str(x[2])
                    for x in con.execute(
                        f"PRAGMA index_info({qident(idx_name)})"
                    ).fetchall()
                ]
                pragma_rows.append({
                    "table": table,
                    "kind": "INDEX",
                    "name": idx_name,
                    "detail": json.dumps({
                        "unique": r[2],
                        "origin": r[3],
                        "partial": r[4],
                        "columns": idx_cols,
                    }, ensure_ascii=False),
                })

        write_csv(
            schema_dir / "key_table_pragmas.csv",
            ["table", "kind", "name", "detail"],
            pragma_rows,
        )

        return {
            "integrity": integrity,
            "fk_errors": len(fk_errors),
            "table_count": len(table_names),
        }

    finally:
        con.close()


def export_route_map(manifest: list[dict]) -> None:
    rows = []
    for item in manifest:
        rel = item["path"]
        if not rel.endswith(".py"):
            continue

        path = ROOT / rel
        txt = text_safe(path)

        try:
            tree = ast.parse(txt)
        except Exception:
            continue

        lines = txt.splitlines()

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue

            decorators = []
            for d in node.decorator_list:
                try:
                    decorators.append(ast.unparse(d))
                except Exception:
                    pass

            route_decos = [
                d for d in decorators
                if ".get(" in d
                or ".post(" in d
                or ".put(" in d
                or ".delete(" in d
                or ".patch(" in d
            ]
            if not route_decos:
                continue

            rows.append({
                "file": rel,
                "function": node.name,
                "line": getattr(node, "lineno", ""),
                "decorators": " | ".join(route_decos),
            })

    write_csv(
        WORK / "_schema" / "route_map.csv",
        ["file", "function", "line", "decorators"],
        rows,
    )


def main() -> int:
    print("=" * 112)
    print("V12 - ĐÓNG GÓI NGUỒN CHỨC NĂNG NẠP HỌC SINH ĐỐI CHIẾU THEO XÃ")
    print("=" * 112)
    print("Chế độ: CHỈ ĐỌC")

    if not ROOT.exists():
        print(f"Không tìm thấy dự án: {ROOT}")
        return 2

    if WORK.exists():
        raise RuntimeError(f"Thư mục tạm đã tồn tại: {WORK}")

    WORK.mkdir(parents=True)

    try:
        print("[1/4] Thu thập mã nguồn liên quan...")
        manifest = collect_source_files()

        print("[2/4] Xuất schema + metadata an toàn...")
        db_info = export_schema_and_metadata()

        print("[3/4] Lập route map...")
        export_route_map(manifest)

        manifest_path = WORK / "_schema" / "source_manifest.csv"
        write_csv(
            manifest_path,
            ["path", "size"],
            manifest,
        )

        summary = {
            "timestamp": STAMP,
            "project": str(ROOT),
            "source_files": len(manifest),
            "database_integrity": db_info["integrity"],
            "database_fk_errors": db_info["fk_errors"],
            "database_tables": db_info["table_count"],
            "database_included": False,
            "student_personal_data_included": False,
            "purpose": (
                "Build official V12 installer for commune-level "
                "student reconciliation source import."
            ),
        }

        (WORK / "_schema" / "SUMMARY.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        print("[4/4] Nén ZIP...")
        with zipfile.ZipFile(
            ZIP_OUT,
            "w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=6,
        ) as zf:
            for path in sorted(WORK.rglob("*")):
                if path.is_file():
                    zf.write(
                        path,
                        arcname=str(path.relative_to(WORK)).replace("\\", "/"),
                    )

        print()
        print("=" * 112)
        print("ĐÓNG GÓI V12 THÀNH CÔNG")
        print("=" * 112)
        print(f"Source files: {len(manifest)}")
        print(f"DB integrity: {db_info['integrity']}")
        print(f"DB FK errors: {db_info['fk_errors']}")
        print("Database thật trong ZIP: KHÔNG")
        print("Dữ liệu cá nhân học sinh trong ZIP: KHÔNG")
        print(f"ZIP: {ZIP_OUT}")
        return 0

    finally:
        # Xóa thư mục tạm, chỉ giữ ZIP.
        if WORK.exists():
            import shutil
            shutil.rmtree(WORK, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
