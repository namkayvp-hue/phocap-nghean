# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
import hashlib
import os
import sqlite3
from datetime import datetime
from pathlib import Path

PROJECT = Path(os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")).resolve()
SURVEYS = PROJECT / "app" / "routers" / "surveys.py"
WORKFLOW = PROJECT / "app" / "routers" / "survey_school_workflow.py"
TEMPLATE = PROJECT / "app" / "templates" / "surveys" / "bulk_assignments.html"
DB = PROJECT / "data" / "phocap.db"
EXPORTS = PROJECT / "exports"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
REPORT = EXPORTS / f"khao_sat_dong_bo_giao_phieu_truong_giao_vien_{STAMP}.txt"

BATCH_ID = int(os.environ.get("PHOCAP_TEST_BATCH_ID", "114"))
SCHOOL_ID = int(os.environ.get("PHOCAP_TEST_SCHOOL_ID", "1607"))

FUNCTION_NAMES = (
    "trang_giao_phieu_cho_truong",
    "luu_giao_phieu_cho_truong",
    "trang_giao_phieu_cho_giao_vien",
    "luu_giao_phieu_cho_giao_vien",
    "hien_thi_trang_phan_cong_v4",
    "luu_phan_cong_v4_theo_cap",
    "dieu_kien_phieu_da_giao_truong",
    "lay_lich_su_giao_truong",
    "lay_lich_su_giao_giao_vien",
)

KEYWORDS = (
    "giao-phieu-truong",
    "giao-phieu-giao-vien",
    "V4_SCHOOL_REPLACE",
    "V4_SCHOOL_CLEAR",
    "V4_TEACHER_REPLACE",
    "V4_TEACHER_CLEAR",
    "V4_TEACHER_ADD",
    "Chưa giao trường",
    "Đã giao",
    "Chưa giao cho trường nào",
    "dieu_kien_phieu_da_giao_truong",
    "SurveyFormInvestigator",
)

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="strict")

def function_map(source: str):
    tree = ast.parse(source)
    result = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            result.setdefault(node.name, []).append(node)
    return result

def get_segment(source: str, node: ast.AST) -> str:
    seg = ast.get_source_segment(source, node)
    if seg:
        return seg
    lines = source.splitlines()
    return "\n".join(lines[int(node.lineno)-1:int(node.end_lineno)])

def table_exists(con, table):
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone() is not None

def columns(con, table):
    return [row[1] for row in con.execute(f'PRAGMA table_info("{table}")').fetchall()]

def row_to_text(row):
    return " | ".join(f"{k}={row[k]!r}" for k in row.keys())

def main():
    print("=" * 112)
    print("KHẢO SÁT ĐỒNG BỘ GIAO PHIẾU: XÃ -> TRƯỜNG -> GIÁO VIÊN")
    print("=" * 112)
    print("Chỉ đọc source + database.")
    print()

    for path in (SURVEYS, WORKFLOW, TEMPLATE, DB):
        if not path.exists():
            print(f"[LỖI] Không tìm thấy: {path}")
            return 1

    db_hash_before = sha256_file(DB)
    source_hashes_before = {
        str(SURVEYS.relative_to(PROJECT)): sha256_file(SURVEYS),
        str(WORKFLOW.relative_to(PROJECT)): sha256_file(WORKFLOW),
        str(TEMPLATE.relative_to(PROJECT)): sha256_file(TEMPLATE),
    }

    surveys_text = read_text(SURVEYS)
    workflow_text = read_text(WORKFLOW)
    template_text = read_text(TEMPLATE)
    ast.parse(surveys_text)
    ast.parse(workflow_text)

    lines = [
        "=" * 130,
        "KHẢO SÁT ĐỒNG BỘ GIAO PHIẾU: XÃ -> TRƯỜNG -> GIÁO VIÊN",
        "=" * 130,
        "",
        f"Project: {PROJECT}",
        f"Batch kiểm tra: {BATCH_ID}",
        f"School kiểm tra: {SCHOOL_ID}",
        "",
        "SOURCE SHA256:",
    ]
    for rel, value in source_hashes_before.items():
        lines.append(f" - {rel}: {value}")

    lines += ["", "I. CÁC HÀM LIÊN QUAN TRONG surveys.py", "=" * 130]

    fmap = function_map(surveys_text)
    for name in FUNCTION_NAMES:
        nodes = fmap.get(name, [])
        lines += ["", f"### {name} | count={len(nodes)} ###"]
        if not nodes:
            lines.append("[KHÔNG TÌM THẤY]")
        for node in nodes:
            lines.append(f"Dòng {node.lineno}-{node.end_lineno}")
            lines.append(get_segment(surveys_text, node))

    lines += ["", "II. DÒNG SOURCE CHỨA TỪ KHÓA GIAO PHIẾU", "=" * 130]
    for no, text in enumerate(surveys_text.splitlines(), start=1):
        if any(keyword.lower() in text.lower() for keyword in KEYWORDS):
            lines.append(f"{no}: {text.rstrip()}")

    lines += ["", "III. TEMPLATE bulk_assignments.html", "=" * 130]
    for no, text in enumerate(template_text.splitlines(), start=1):
        if any(
            token.lower() in text.lower()
            for token in (
                "Giao phiếu",
                "Giao lại",
                "Đã giao",
                "Chưa giao",
                "assignment_level",
                "mode",
                "Nhật ký",
            )
        ):
            lines.append(f"{no}: {text.rstrip()}")

    uri = DB.resolve().as_uri() + "?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    con.row_factory = sqlite3.Row

    try:
        con.execute("PRAGMA query_only = ON")
        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
        fk = con.execute("PRAGMA foreign_key_check").fetchall()

        lines += [
            "",
            "IV. DATABASE HEALTH",
            "=" * 130,
            f"integrity_check={integrity}",
            f"foreign_key_check={len(fk)}",
            "",
            "V. BATCH / SCHOOL KIỂM TRA",
            "=" * 130,
        ]

        if table_exists(con, "survey_batches"):
            for row in con.execute("SELECT * FROM survey_batches WHERE id=?", (BATCH_ID,)).fetchall():
                lines.append("survey_batches: " + row_to_text(row))

        if table_exists(con, "survey_school_assignments"):
            for row in con.execute(
                "SELECT * FROM survey_school_assignments WHERE survey_batch_id=? AND school_id=? ORDER BY id DESC",
                (BATCH_ID, SCHOOL_ID),
            ).fetchall():
                lines.append("survey_school_assignments: " + row_to_text(row))

        if table_exists(con, "survey_execution_workflow_logs"):
            for row in con.execute(
                "SELECT * FROM survey_execution_workflow_logs WHERE survey_batch_id=? AND (school_id=? OR school_id IS NULL) ORDER BY id DESC LIMIT 50",
                (BATCH_ID, SCHOOL_ID),
            ).fetchall():
                lines.append("survey_execution_workflow_logs: " + row_to_text(row))

        lines += ["", "VI. BẢNG PHÂN CÔNG/NHẬT KÝ CÓ DỮ LIỆU BATCH", "=" * 130]
        tables = [
            row[0]
            for row in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
        ]
        for table in tables:
            cols = columns(con, table)
            search = (table + " " + " ".join(cols)).lower()
            if not any(token in search for token in ("assign", "investigator", "history", "workflow_log")):
                continue
            if "survey_batch_id" not in cols and "batch_id" not in cols:
                continue
            batch_col = "survey_batch_id" if "survey_batch_id" in cols else "batch_id"
            try:
                rows = con.execute(
                    f'SELECT * FROM "{table}" WHERE "{batch_col}"=? ORDER BY id DESC LIMIT 80',
                    (BATCH_ID,),
                ).fetchall()
            except Exception:
                continue
            if not rows:
                continue
            lines.append("")
            lines.append(f"TABLE {table} | columns={', '.join(cols)}")
            for row in rows:
                lines.append(" - " + row_to_text(row))

    finally:
        con.close()

    db_hash_after = sha256_file(DB)
    source_hashes_after = {
        str(SURVEYS.relative_to(PROJECT)): sha256_file(SURVEYS),
        str(WORKFLOW.relative_to(PROJECT)): sha256_file(WORKFLOW),
        str(TEMPLATE.relative_to(PROJECT)): sha256_file(TEMPLATE),
    }

    lines += [
        "",
        "VII. AN TOÀN SAU KHẢO SÁT",
        "=" * 130,
        f"DB SHA trước: {db_hash_before}",
        f"DB SHA sau  : {db_hash_after}",
        "Database: " + ("KHÔNG THAY ĐỔI" if db_hash_before == db_hash_after else "ĐÃ THAY ĐỔI"),
    ]

    source_same = True
    for rel in source_hashes_before:
        same = source_hashes_before[rel] == source_hashes_after[rel]
        source_same = source_same and same
        lines.append(f"{rel}: " + ("KHÔNG THAY ĐỔI" if same else "ĐÃ THAY ĐỔI"))

    if db_hash_before != db_hash_after or not source_same:
        raise RuntimeError("Source/database thay đổi trong khảo sát.")

    EXPORTS.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines), encoding="utf-8-sig")

    print("[1/5] Source surveys/workflow: AST OK.")
    print("[2/5] Đã lấy route/helper giao trường/giao giáo viên.")
    print("[3/5] Đã đối chiếu DB batch 114 / school 1607.")
    print("[4/5] Source + Database: KHÔNG THAY ĐỔI.")
    print(f"[5/5] Báo cáo: {REPORT}")
    print()
    print("KHẢO SÁT HOÀN TẤT - CHƯA SỬA GÌ.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
