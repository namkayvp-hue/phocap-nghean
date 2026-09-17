# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
import hashlib
import json
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(r"C:\PhoCap")
APP = ROOT / "app"
DB = ROOT / "data" / "phocap.db"

SURVEYS = APP / "routers" / "surveys.py"
DATABASE = APP / "database.py"
MODEL = APP / "survey_models.py"
YEAR_TEMPLATE = APP / "templates" / "surveys" / "year_records.html"

EXPORTS = ROOT / "exports"
OUT = EXPORTS / "KHAO_SAT_LUONG_LUU_NOI_HOC_KHUYET_TAT_26D.txt"
JSON_OUT = EXPORTS / "KHAO_SAT_LUONG_LUU_NOI_HOC_KHUYET_TAT_26D.json"

EXPECTED_DB_SHA = "cb821b5500b239756ff4b745b8f36abfaa8a44b9f43de00c26a64cd9db81ce26"

TEST_PERSON_ID = 76
TEST_SCHOOL_YEAR_ID = 2

TARGET_FIELDS = (
    "study_location_scope",
    "disability_status",
    "disability_can_learn",
    "disability_access_education",
)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def log(f, *parts):
    line = " ".join(str(x) for x in parts)
    print(line)
    f.write(line + "\n")
    f.flush()


def line_numbered(text: str, start_line: int = 1) -> str:
    return "\n".join(
        f"{start_line + i:05d}: {line}"
        for i, line in enumerate(text.splitlines())
    )


def function_node_and_source(source: str, name: str):
    tree = ast.parse(source)
    nodes = [
        n for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        and n.name == name
    ]
    if len(nodes) != 1:
        raise RuntimeError(
            f"Cần đúng 1 hàm {name}, thực tế={len(nodes)}."
        )

    node = nodes[0]
    seg = ast.get_source_segment(source, node)
    if seg is None:
        raise RuntimeError(f"Không lấy được source hàm {name}.")
    return node, seg


def source_context_hits(source: str, needles: tuple[str, ...], context: int = 6):
    lines = source.splitlines()
    results = []
    seen = set()

    for idx, line in enumerate(lines):
        low = line.lower()
        matched = [n for n in needles if n.lower() in low]
        if not matched:
            continue

        start = max(0, idx - context)
        end = min(len(lines), idx + context + 1)
        key = (start, end)
        if key in seen:
            continue
        seen.add(key)

        results.append({
            "line": idx + 1,
            "matched": matched,
            "snippet": "\n".join(
                f"{j+1:05d}: {lines[j]}"
                for j in range(start, end)
            ),
        })

    return results


def ast_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = ast_name(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    if isinstance(node, ast.Call):
        return ast_name(node.func)
    if isinstance(node, ast.Subscript):
        return ast_name(node.value)
    return ""


def analyze_function(node: ast.AST, source: str) -> dict[str, Any]:
    result: dict[str, Any] = {
        "parameters": [],
        "db_calls": [],
        "target_field_assignments": [],
        "calls": [],
        "returns": [],
        "record_like_names": [],
    }

    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        all_args = (
            list(node.args.posonlyargs)
            + list(node.args.args)
            + list(node.args.kwonlyargs)
        )
        result["parameters"] = [a.arg for a in all_args]

    record_names = set()

    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            call_name = ast_name(child.func)
            if call_name:
                result["calls"].append({
                    "line": getattr(child, "lineno", None),
                    "name": call_name,
                })
                if (
                    call_name.startswith("db.")
                    or call_name.startswith("session.")
                    or ".commit" in call_name
                    or ".flush" in call_name
                    or ".execute" in call_name
                    or ".add" in call_name
                    or ".merge" in call_name
                    or ".refresh" in call_name
                    or ".rollback" in call_name
                ):
                    result["db_calls"].append({
                        "line": getattr(child, "lineno", None),
                        "name": call_name,
                        "source": ast.get_source_segment(source, child),
                    })

        if isinstance(child, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            targets = []
            if isinstance(child, ast.Assign):
                targets = child.targets
            else:
                targets = [child.target]

            for target in targets:
                tname = ast_name(target)
                if not tname:
                    continue

                if any(
                    tname.endswith("." + field) or tname == field
                    for field in TARGET_FIELDS
                ):
                    result["target_field_assignments"].append({
                        "line": getattr(child, "lineno", None),
                        "target": tname,
                        "source": ast.get_source_segment(source, child),
                    })

                if "." in tname:
                    base = tname.split(".", 1)[0]
                    if base in {"record", "form_record", "selected_record", "year_record"}:
                        record_names.add(base)

        if isinstance(child, ast.Return):
            result["returns"].append({
                "line": getattr(child, "lineno", None),
                "source": ast.get_source_segment(source, child),
            })

    result["record_like_names"] = sorted(record_names)

    # Deduplicate calls while retaining order.
    seen = set()
    deduped = []
    for item in result["calls"]:
        key = (item["line"], item["name"])
        if key not in seen:
            seen.add(key)
            deduped.append(item)
    result["calls"] = deduped

    return result


def find_function_defs_in_file(source: str, names: tuple[str, ...]) -> list[dict[str, Any]]:
    tree = ast.parse(source)
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name not in names:
            continue
        seg = ast.get_source_segment(source, node) or ""
        out.append({
            "name": node.name,
            "line": node.lineno,
            "source": seg,
        })
    return out


def all_python_hits(root: Path, needles: tuple[str, ...]) -> list[dict[str, Any]]:
    results = []
    for p in root.rglob("*.py"):
        if any(x in p.parts for x in (".venv", "venv", "__pycache__", "backups", "exports")):
            continue
        try:
            if p.stat().st_size > 4 * 1024 * 1024:
                continue
            text = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        hits = source_context_hits(text, needles, context=4)
        if hits:
            results.append({
                "file": str(p.relative_to(ROOT)),
                "hits": hits[:60],
            })
    return results


def qrow(cur):
    row = cur.fetchone()
    if row is None:
        return None
    names = [d[0] for d in cur.description]
    return dict(zip(names, row))


def qrows(cur):
    names = [d[0] for d in cur.description]
    return [dict(zip(names, r)) for r in cur.fetchall()]


def table_exists(con: sqlite3.Connection, table: str) -> bool:
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone() is not None


def cols(con: sqlite3.Connection, table: str) -> list[str]:
    if not table_exists(con, table):
        return []
    return [
        str(r[1])
        for r in con.execute(f'PRAGMA table_info("{table}")').fetchall()
    ]


def db_audit() -> dict[str, Any]:
    con = sqlite3.connect(
        f"file:{DB.as_posix()}?mode=ro",
        uri=True,
        timeout=30,
    )
    con.row_factory = sqlite3.Row

    try:
        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
        fk = con.execute("PRAGMA foreign_key_check").fetchall()

        if integrity != "ok" or fk:
            raise RuntimeError(
                f"DB health không đạt: integrity={integrity}, FK={len(fk)}"
            )

        result: dict[str, Any] = {
            "integrity": integrity,
            "fk_count": len(fk),
            "tables": {},
            "test_record": None,
            "test_person": None,
            "test_household": None,
            "test_forms": [],
            "target_field_stats": {},
        }

        for table in (
            "survey_person_year_records",
            "survey_people",
            "households",
            "survey_forms",
        ):
            result["tables"][table] = {
                "exists": table_exists(con, table),
                "columns": cols(con, table),
            }

        if table_exists(con, "survey_person_year_records"):
            result["test_record"] = qrow(con.execute(
                """
                SELECT *
                FROM survey_person_year_records
                WHERE survey_person_id=?
                  AND school_year_id=?
                ORDER BY id DESC
                LIMIT 1
                """,
                (TEST_PERSON_ID, TEST_SCHOOL_YEAR_ID),
            ))

            result["target_field_stats"] = qrow(con.execute(
                """
                SELECT
                    COUNT(*) AS year_record_total,
                    SUM(CASE WHEN study_location_scope IS NULL
                                  OR TRIM(COALESCE(study_location_scope,''))=''
                             THEN 1 ELSE 0 END) AS study_location_blank,
                    SUM(CASE WHEN disability_status='CO_KHUYET_TAT'
                                  THEN 1 ELSE 0 END) AS disabled_total,
                    SUM(CASE WHEN disability_status='CO_KHUYET_TAT'
                                  AND disability_can_learn IS NULL
                             THEN 1 ELSE 0 END) AS disabled_can_learn_null,
                    SUM(CASE WHEN disability_status='CO_KHUYET_TAT'
                                  AND disability_access_education IS NULL
                             THEN 1 ELSE 0 END) AS disabled_access_null
                FROM survey_person_year_records
                """
            ))

        if table_exists(con, "survey_people"):
            pcols = cols(con, "survey_people")
            if "id" in pcols:
                result["test_person"] = qrow(con.execute(
                    "SELECT * FROM survey_people WHERE id=?",
                    (TEST_PERSON_ID,),
                ))

        household_id = None
        if result["test_person"]:
            household_id = result["test_person"].get("household_id")

        if household_id is not None and table_exists(con, "households"):
            result["test_household"] = qrow(con.execute(
                "SELECT * FROM households WHERE id=?",
                (household_id,),
            ))

        if household_id is not None and table_exists(con, "survey_forms"):
            sf_cols = cols(con, "survey_forms")
            if "household_id" in sf_cols:
                result["test_forms"] = qrows(con.execute(
                    """
                    SELECT *
                    FROM survey_forms
                    WHERE household_id=?
                    ORDER BY id
                    """,
                    (household_id,),
                ))

        return result
    finally:
        con.close()


def main():
    EXPORTS.mkdir(parents=True, exist_ok=True)

    with OUT.open("w", encoding="utf-8-sig", newline="\n") as f:
        log(f, "=" * 170)
        log(f, "FIX 26D - KHẢO SÁT CHÍNH XÁC LUỒNG LƯU NƠI HỌC + KHUYẾT TẬT")
        log(f, "CHỈ ĐỌC SOURCE + DATABASE. KHÔNG SỬA SOURCE. KHÔNG GHI DATABASE.")
        log(f, "=" * 170)

        for p in (DB, SURVEYS, YEAR_TEMPLATE, MODEL):
            if not p.exists():
                raise RuntimeError(f"Không tìm thấy: {p}")

        db_sha = sha256_file(DB)
        log(f, "DB_SHA =", db_sha)
        log(f, "EXPECTED_DB_SHA =", EXPECTED_DB_SHA)
        if db_sha != EXPECTED_DB_SHA:
            raise RuntimeError(
                "DB SHA khác nền sau lần FIX26C dừng an toàn."
            )

        audit: dict[str, Any] = {
            "db_sha": db_sha,
            "test_person_id": TEST_PERSON_ID,
            "test_school_year_id": TEST_SCHOOL_YEAR_ID,
        }

        dbinfo = db_audit()
        audit["db"] = dbinfo

        log(f, "INTEGRITY =", dbinfo["integrity"])
        log(f, "FK_COUNT =", dbinfo["fk_count"])
        log(f, "TARGET_FIELD_STATS =", json.dumps(
            dbinfo["target_field_stats"],
            ensure_ascii=False,
            default=str,
        ))
        log(f, "TEST_RECORD =", json.dumps(
            dbinfo["test_record"],
            ensure_ascii=False,
            default=str,
        ))
        log(f, "TEST_PERSON =", json.dumps(
            dbinfo["test_person"],
            ensure_ascii=False,
            default=str,
        ))

        surveys_text = SURVEYS.read_text(encoding="utf-8-sig")
        node, fn_source = function_node_and_source(
            surveys_text,
            "luu_theo_doi_nam_hoc",
        )
        fn_analysis = analyze_function(node, surveys_text)

        audit["save_function"] = {
            "line_start": node.lineno,
            "line_end": node.end_lineno,
            "source": fn_source,
            "analysis": fn_analysis,
        }

        log(f, "")
        log(f, "=" * 170)
        log(f, "1. TOÀN BỘ HÀM luu_theo_doi_nam_hoc")
        log(f, "=" * 170)
        log(f, line_numbered(fn_source, node.lineno))

        log(f, "")
        log(f, "=" * 170)
        log(f, "2. PHÂN TÍCH AST HÀM LƯU")
        log(f, "=" * 170)
        log(f, "PARAMETERS =", fn_analysis["parameters"])
        log(f, "RECORD_LIKE_NAMES =", fn_analysis["record_like_names"])
        log(f, "DB_CALLS =", json.dumps(
            fn_analysis["db_calls"],
            ensure_ascii=False,
            indent=2,
            default=str,
        ))
        log(f, "TARGET_FIELD_ASSIGNMENTS =", json.dumps(
            fn_analysis["target_field_assignments"],
            ensure_ascii=False,
            indent=2,
            default=str,
        ))

        field_hits = source_context_hits(
            surveys_text,
            TARGET_FIELDS
            + (
                "luu_theo_doi_nam_hoc",
                "db.flush",
                "db.commit",
                "db.execute",
                "db.add",
                "db.refresh",
                "db.rollback",
            ),
            context=6,
        )
        audit["surveys_context_hits"] = field_hits

        log(f, "")
        log(f, "=" * 170)
        log(f, "3. CÁC ĐOẠN SOURCE LIÊN QUAN TRONG surveys.py")
        log(f, "=" * 170)
        for hit in field_hits:
            log(f, hit["snippet"])
            log(f, "-" * 120)

        database_text = ""
        if DATABASE.exists():
            database_text = DATABASE.read_text(
                encoding="utf-8",
                errors="ignore",
            )

        db_helpers = []
        if database_text:
            db_helpers = find_function_defs_in_file(
                database_text,
                (
                    "get_db",
                    "get_session",
                    "session_scope",
                    "get_database",
                ),
            )

        audit["database_helpers"] = db_helpers

        log(f, "")
        log(f, "=" * 170)
        log(f, "4. DATABASE DEPENDENCY / CÁCH SESSION ĐƯỢC KẾT THÚC")
        log(f, "=" * 170)
        if db_helpers:
            for item in db_helpers:
                log(f, f"FILE=app/database.py FUNCTION={item['name']} LINE={item['line']}")
                log(f, line_numbered(item["source"], item["line"]))
                log(f, "-" * 120)
        else:
            log(f, "Không tìm thấy helper get_db/get_session/session_scope trong app/database.py.")

        project_hits = all_python_hits(
            APP,
            TARGET_FIELDS
            + (
                "def get_db",
                "yield db",
                "yield session",
                "db.commit()",
                "session.commit()",
                "SurveyPersonYearRecord",
            ),
        )
        audit["project_hits"] = project_hits

        log(f, "")
        log(f, "=" * 170)
        log(f, "5. CÁC FILE PYTHON KHÁC CÓ LIÊN QUAN")
        log(f, "=" * 170)
        for item in project_hits:
            log(f, "FILE =", item["file"])
            for hit in item["hits"][:30]:
                log(f, hit["snippet"])
                log(f, "-" * 100)

        template_text = YEAR_TEMPLATE.read_text(
            encoding="utf-8",
            errors="ignore",
        )
        template_hits = source_context_hits(
            template_text,
            TARGET_FIELDS,
            context=5,
        )
        audit["template_hits"] = template_hits

        log(f, "")
        log(f, "=" * 170)
        log(f, "6. FORM FIELD TRONG year_records.html")
        log(f, "=" * 170)
        for hit in template_hits:
            log(f, hit["snippet"])
            log(f, "-" * 100)

        JSON_OUT.write_text(
            json.dumps(
                audit,
                ensure_ascii=False,
                indent=2,
                default=str,
            ),
            encoding="utf-8-sig",
        )

        log(f, "")
        log(f, "=" * 170)
        log(f, "KẾT LUẬN FIX26D")
        log(f, "=" * 170)
        log(f, "DATABASE_WRITES_THIS_RUN = 0")
        log(f, "SOURCE_WRITES_THIS_RUN = 0")
        log(f, "DB_SHA_AFTER_READ_ONLY =", sha256_file(DB))
        log(f, "JSON_OUT =", JSON_OUT)
        log(f, "FIX26D_SUCCESS = YES")
        log(f, "NEXT = Dùng đúng output này để viết FIX26E theo cơ chế lưu thật của project; không đoán commit nữa.")
        log(f, "=" * 170)

    return 0


if __name__ == "__main__":
    try:
        rc = main()
    except Exception as exc:
        try:
            EXPORTS.mkdir(parents=True, exist_ok=True)
            with OUT.open("a", encoding="utf-8-sig", newline="\n") as f:
                log(f, "")
                log(f, "=" * 170)
                log(f, "FIX26D_SUCCESS = NO")
                log(f, "ERROR =", repr(exc))
                if DB.exists():
                    log(f, "DB_SHA_CURRENT =", sha256_file(DB))
                log(f, "DỪNG AN TOÀN.")
                log(f, "=" * 170)
        except Exception:
            print("ERROR =", repr(exc))
        rc = 1

    raise SystemExit(rc)
