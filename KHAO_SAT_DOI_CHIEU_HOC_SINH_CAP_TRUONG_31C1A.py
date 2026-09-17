# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
import hashlib
import json
import sqlite3
import sys
import unicodedata
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(r"C:\PhoCap")
APP = ROOT / "app"
DB = ROOT / "data" / "phocap.db"
EXPORTS = ROOT / "exports"

OUT = EXPORTS / "KHAO_SAT_DOI_CHIEU_HOC_SINH_CAP_TRUONG_31C1A.txt"
JSON_OUT = EXPORTS / "KHAO_SAT_DOI_CHIEU_HOC_SINH_CAP_TRUONG_31C1A.json"

TARGET_SCHOOL_NAME = "Trường Mầm non Nghi Diễn"
CURRENT_YEAR_ID = 2       # 2026-2027
BASELINE_YEAR_ID = 1      # 2025-2026

COMPARISON_MODULE = APP / "routers" / "student_survey_comparison.py"

SEARCH_TERMS = [
    "Đối chiếu điều tra với học sinh",
    "Đối chiếu học sinh",
    "doi-chieu",
    "doi_chieu",
    "student_survey_comparison",
    "school_id",
    "school_year_id",
    "2025-2026",
    "2026-2027",
    "previous",
    "baseline",
    "source_year",
    "match",
    "khớp",
    "không khớp",
    "thiếu",
    "thừa",
]


def log(f, *parts):
    line = " ".join(str(x) for x in parts)
    print(line)
    f.write(line + "\n")
    f.flush()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as src:
        for block in iter(lambda: src.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def normalize_vi(s: str) -> str:
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    return s.casefold().strip()


def context(text: str, line_no: int, before: int = 8, after: int = 16) -> str:
    lines = text.splitlines()
    a = max(1, line_no - before)
    b = min(len(lines), line_no + after)
    return "\n".join(f"{i:05d}: {lines[i-1]}" for i in range(a, b + 1))


def text_files():
    exts = {".py", ".html", ".htm", ".jinja", ".j2", ".js"}
    for p in APP.rglob("*"):
        if not p.is_file():
            continue
        if "__pycache__" in p.parts:
            continue
        if p.suffix.lower() not in exts:
            continue
        yield p


def search_source():
    hits = []
    for p in text_files():
        try:
            txt = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        low = txt.casefold()
        for term in SEARCH_TERMS:
            needle = term.casefold()
            pos = 0
            per_term = 0
            while True:
                idx = low.find(needle, pos)
                if idx < 0:
                    break
                line_no = txt.count("\n", 0, idx) + 1
                hits.append({
                    "file": str(p.relative_to(ROOT)),
                    "term": term,
                    "line": line_no,
                    "context": context(txt, line_no),
                })
                pos = idx + max(1, len(needle))
                per_term += 1
                if per_term >= 30:
                    break
    return hits


def inspect_comparison_module():
    result = {
        "exists": COMPARISON_MODULE.exists(),
        "sha256": None,
        "routes": [],
        "functions": [],
        "source_year_evidence": [],
        "school_scope_evidence": [],
        "matching_evidence": [],
    }

    if not COMPARISON_MODULE.exists():
        return result

    text = COMPARISON_MODULE.read_text(encoding="utf-8-sig", errors="ignore")
    result["sha256"] = sha256_file(COMPARISON_MODULE)

    try:
        tree = ast.parse(text)
    except Exception as exc:
        result["parse_error"] = repr(exc)
        return result

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            decorators = []
            for d in node.decorator_list:
                try:
                    decorators.append(ast.unparse(d))
                except Exception:
                    decorators.append("<unparse-failed>")

            if decorators:
                result["routes"].append({
                    "function": node.name,
                    "line": node.lineno,
                    "decorators": decorators,
                    "context": context(text, node.lineno, before=4, after=18),
                })

            if any(k in node.name.casefold() for k in (
                "compare", "comparison", "doi_chieu", "match",
                "school", "student", "source", "year"
            )):
                result["functions"].append({
                    "name": node.name,
                    "line": node.lineno,
                })

    for pattern, bucket in (
        ("2025-2026", "source_year_evidence"),
        ("2026-2027", "source_year_evidence"),
        ("school_year_id", "source_year_evidence"),
        ("previous", "source_year_evidence"),
        ("baseline", "source_year_evidence"),
        ("source_year", "source_year_evidence"),
        ("school_id", "school_scope_evidence"),
        ("role_code", "school_scope_evidence"),
        ("TRUONG", "school_scope_evidence"),
        ("full_name", "matching_evidence"),
        ("date_of_birth", "matching_evidence"),
        ("personal_id", "matching_evidence"),
        ("citizen_id", "matching_evidence"),
        ("student_code", "matching_evidence"),
        ("match", "matching_evidence"),
    ):
        start = 0
        count = 0
        low = text.casefold()
        needle = pattern.casefold()
        while True:
            idx = low.find(needle, start)
            if idx < 0:
                break
            line_no = text.count("\n", 0, idx) + 1
            result[bucket].append({
                "pattern": pattern,
                "line": line_no,
                "context": context(text, line_no, 6, 12),
            })
            start = idx + max(1, len(needle))
            count += 1
            if count >= 20:
                break

    return result


def table_names(con):
    return [
        r[0] for r in con.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
            "ORDER BY name"
        ).fetchall()
    ]


def table_columns(con, table):
    return [r[1] for r in con.execute(f'PRAGMA table_info("{table}")').fetchall()]


def safe_count(con, table, where="", params=()):
    q = f'SELECT COUNT(*) FROM "{table}"'
    if where:
        q += " WHERE " + where
    try:
        return int(con.execute(q, params).fetchone()[0])
    except Exception:
        return None


def inspect_db():
    con = sqlite3.connect(
        f"file:{DB.as_posix()}?mode=ro",
        uri=True,
        timeout=30,
    )
    con.row_factory = sqlite3.Row

    try:
        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
        fk = con.execute("PRAGMA foreign_key_check").fetchall()
        tables = table_names(con)

        years = []
        if "school_years" in tables:
            try:
                years = [
                    dict(r) for r in con.execute(
                        "SELECT * FROM school_years ORDER BY id"
                    ).fetchall()
                ]
            except Exception:
                pass

        school_candidates = []
        if "schools" in tables:
            cols = table_columns(con, "schools")
            if "id" in cols and "name" in cols:
                target = normalize_vi(TARGET_SCHOOL_NAME)
                for r in con.execute("SELECT id, name FROM schools ORDER BY id").fetchall():
                    name_norm = normalize_vi(r["name"])
                    if "nghi dien" in name_norm or target in name_norm:
                        school_candidates.append(dict(r))

        school_ids = [int(x["id"]) for x in school_candidates]

        student_like_tables = []
        keywords = ("student", "pupil", "hoc_sinh", "enroll", "class")
        for table in tables:
            cols = table_columns(con, table)
            low_table = table.casefold()
            if (
                any(k in low_table for k in keywords)
                or any(any(k in c.casefold() for k in keywords) for c in cols)
            ):
                student_like_tables.append({
                    "table": table,
                    "columns": cols,
                })

        counts = []
        for item in student_like_tables:
            table = item["table"]
            cols = item["columns"]

            school_col = next(
                (c for c in ("school_id", "assigned_school_id") if c in cols),
                None,
            )
            year_col = next(
                (c for c in ("school_year_id", "year_id") if c in cols),
                None,
            )

            row = {
                "table": table,
                "total": safe_count(con, table),
                "school_column": school_col,
                "year_column": year_col,
            }

            if year_col:
                row["baseline_2025_2026"] = safe_count(
                    con, table, f'"{year_col}"=?', (BASELINE_YEAR_ID,)
                )
                row["current_2026_2027"] = safe_count(
                    con, table, f'"{year_col}"=?', (CURRENT_YEAR_ID,)
                )

            if school_col and school_ids:
                placeholders = ",".join("?" for _ in school_ids)
                row["target_school_all_years"] = safe_count(
                    con,
                    table,
                    f'"{school_col}" IN ({placeholders})',
                    tuple(school_ids),
                )
                if year_col:
                    row["target_school_baseline"] = safe_count(
                        con,
                        table,
                        f'"{school_col}" IN ({placeholders}) AND "{year_col}"=?',
                        tuple(school_ids) + (BASELINE_YEAR_ID,),
                    )
                    row["target_school_current"] = safe_count(
                        con,
                        table,
                        f'"{school_col}" IN ({placeholders}) AND "{year_col}"=?',
                        tuple(school_ids) + (CURRENT_YEAR_ID,),
                    )

            counts.append(row)

        survey_counts = {}
        if "survey_person_year_records" in tables:
            cols = table_columns(con, "survey_person_year_records")
            survey_counts["total"] = safe_count(con, "survey_person_year_records")
            if "school_year_id" in cols:
                survey_counts["baseline"] = safe_count(
                    con,
                    "survey_person_year_records",
                    '"school_year_id"=?',
                    (BASELINE_YEAR_ID,),
                )
                survey_counts["current"] = safe_count(
                    con,
                    "survey_person_year_records",
                    '"school_year_id"=?',
                    (CURRENT_YEAR_ID,),
                )
            if "school_id" in cols and school_ids:
                placeholders = ",".join("?" for _ in school_ids)
                survey_counts["target_school_current"] = safe_count(
                    con,
                    "survey_person_year_records",
                    f'"school_id" IN ({placeholders}) AND "school_year_id"=?',
                    tuple(school_ids) + (CURRENT_YEAR_ID,),
                )

        identity_tables = []
        identity_names = {
            "full_name", "name", "date_of_birth", "birth_date",
            "personal_id", "citizen_id", "student_code",
            "school_id", "class_id", "school_year_id",
        }
        for table in tables:
            cols = table_columns(con, table)
            matched = [c for c in cols if c.casefold() in identity_names]
            if len(matched) >= 2 and (
                "student" in table.casefold()
                or table in {"survey_people", "survey_person_year_records"}
            ):
                identity_tables.append({
                    "table": table,
                    "identity_columns": matched,
                })

    finally:
        con.close()

    if integrity != "ok" or fk:
        raise RuntimeError(
            f"DB health không đạt: integrity={integrity}; FK={len(fk)}"
        )

    return {
        "integrity": integrity,
        "fk_count": len(fk),
        "school_years": years,
        "school_candidates": school_candidates,
        "student_like_tables": student_like_tables,
        "counts": counts,
        "survey_counts": survey_counts,
        "identity_tables": identity_tables,
    }


def classify_source_hits(hits):
    return {
        "route_hits": [
            h for h in hits
            if "@router." in h["context"] or "def " in h["context"]
        ],
        "template_hits": [
            h for h in hits
            if h["file"].lower().endswith((".html", ".htm", ".jinja", ".j2"))
        ],
        "menu_hits": [
            h for h in hits
            if "5.1.3" in h["context"]
            or "2.5." in h["context"]
            or "Đối chiếu" in h["context"]
        ],
    }


def main():
    EXPORTS.mkdir(parents=True, exist_ok=True)

    with OUT.open("w", encoding="utf-8-sig", newline="\n") as f:
        log(f, "=" * 190)
        log(f, "BÀI 31C1A - KHẢO SÁT NGHIỆP VỤ ĐỐI CHIẾU HỌC SINH TỪ CẤP TRƯỜNG")
        log(f, "SỬA LỖI GỌI HÀM context() CỦA 31C1")
        log(f, "CHỈ ĐỌC SOURCE + DATABASE - KHÔNG SỬA SOURCE - KHÔNG GHI DB")
        log(f, "MỤC TIÊU: TẬN DỤNG CHỨC NĂNG ĐỐI CHIẾU ĐÃ CÓ, KHÔNG XÂY TRÙNG")
        log(f, "=" * 190)

        if not DB.exists():
            raise RuntimeError(f"Không tìm thấy DB: {DB}")
        if not APP.exists():
            raise RuntimeError(f"Không tìm thấy APP: {APP}")

        db_sha_before = sha256_file(DB)
        db_info = inspect_db()
        module_info = inspect_comparison_module()
        source_hits = search_source()
        classified = classify_source_hits(source_hits)

        log(f, "DB_SHA_BEFORE =", db_sha_before)
        log(f, "INTEGRITY =", db_info["integrity"])
        log(f, "FK_COUNT =", db_info["fk_count"])
        log(f, "TARGET_SCHOOL =", TARGET_SCHOOL_NAME)
        log(f, "BASELINE_YEAR_ID =", BASELINE_YEAR_ID)
        log(f, "CURRENT_YEAR_ID =", CURRENT_YEAR_ID)

        log(f, "")
        log(f, "=" * 190)
        log(f, "I. MODULE ĐỐI CHIẾU HIỆN CÓ")
        log(f, "=" * 190)
        log(f, "MODULE_EXISTS =", module_info["exists"])
        log(f, "MODULE_SHA =", module_info["sha256"])
        log(f, "ROUTE_COUNT =", len(module_info["routes"]))
        for item in module_info["routes"][:80]:
            log(f, f"--- {item['function']} @ line {item['line']}")
            log(f, "DECORATORS =", item["decorators"])
            log(f, item["context"])

        log(f, "")
        log(f, "SOURCE_YEAR_EVIDENCE_COUNT =", len(module_info["source_year_evidence"]))
        for item in module_info["source_year_evidence"][:80]:
            log(f, f"--- {item['pattern']} @ line {item['line']}")
            log(f, item["context"])

        log(f, "")
        log(f, "SCHOOL_SCOPE_EVIDENCE_COUNT =", len(module_info["school_scope_evidence"]))
        for item in module_info["school_scope_evidence"][:80]:
            log(f, f"--- {item['pattern']} @ line {item['line']}")
            log(f, item["context"])

        log(f, "")
        log(f, "MATCHING_EVIDENCE_COUNT =", len(module_info["matching_evidence"]))
        for item in module_info["matching_evidence"][:80]:
            log(f, f"--- {item['pattern']} @ line {item['line']}")
            log(f, item["context"])

        log(f, "")
        log(f, "=" * 190)
        log(f, "II. MENU / ROUTE / TEMPLATE LIÊN QUAN")
        log(f, "=" * 190)
        log(f, "SOURCE_HIT_COUNT =", len(source_hits))
        log(f, "ROUTE_HIT_COUNT =", len(classified["route_hits"]))
        log(f, "TEMPLATE_HIT_COUNT =", len(classified["template_hits"]))
        log(f, "MENU_HIT_COUNT =", len(classified["menu_hits"]))

        for h in classified["menu_hits"][:80]:
            log(f, f"--- MENU {h['file']}:{h['line']} | TERM={h['term']}")
            log(f, h["context"])

        log(f, "")
        log(f, "=" * 190)
        log(f, "III. DATABASE CỦA TRƯỜNG MẦM NON NGHI DIỄN")
        log(f, "=" * 190)
        log(f, "SCHOOL_CANDIDATES =", json.dumps(
            db_info["school_candidates"], ensure_ascii=False, indent=2, default=str
        ))
        log(f, "STUDENT_TABLE_COUNTS =", json.dumps(
            db_info["counts"], ensure_ascii=False, indent=2, default=str
        ))
        log(f, "SURVEY_COUNTS =", json.dumps(
            db_info["survey_counts"], ensure_ascii=False, indent=2, default=str
        ))
        log(f, "IDENTITY_TABLES =", json.dumps(
            db_info["identity_tables"], ensure_ascii=False, indent=2, default=str
        ))

        has_module = bool(module_info["exists"])
        has_routes = bool(module_info["routes"])
        has_school_scope = bool(module_info["school_scope_evidence"])
        has_source_year = bool(module_info["source_year_evidence"])
        has_matching = bool(module_info["matching_evidence"])

        log(f, "")
        log(f, "=" * 190)
        log(f, "IV. KẾT LUẬN 31C1A")
        log(f, "=" * 190)
        log(f, "EXISTING_COMPARISON_MODULE =", "YES" if has_module else "NO")
        log(f, "EXISTING_COMPARISON_ROUTES =", "YES" if has_routes else "NO")
        log(f, "SCHOOL_SCOPE_LOGIC_FOUND =", "YES" if has_school_scope else "NO")
        log(f, "SOURCE_YEAR_LOGIC_FOUND =", "YES" if has_source_year else "NO")
        log(f, "MATCHING_LOGIC_FOUND =", "YES" if has_matching else "NO")

        if has_module and has_routes:
            log(f, "STRATEGY = REUSE_EXISTING_COMPARISON_FEATURE")
            log(f, "DO_NOT_BUILD_DUPLICATE_FEATURE = YES")
        else:
            log(f, "STRATEGY = DEEPER_AUDIT_REQUIRED")

        log(f, "DATABASE_WRITES_THIS_RUN = 0")
        log(f, "SOURCE_WRITES_THIS_RUN = 0")
        log(f, "DB_SHA_AFTER =", sha256_file(DB))
        log(f, "AUDIT31C1A_SUCCESS = YES")
        log(f, "=" * 190)

        JSON_OUT.write_text(
            json.dumps(
                {
                    "db_sha": db_sha_before,
                    "db_info": db_info,
                    "module_info": module_info,
                    "source_hits": source_hits,
                    "classified": classified,
                },
                ensure_ascii=False,
                indent=2,
                default=str,
            ),
            encoding="utf-8-sig",
        )

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        try:
            EXPORTS.mkdir(parents=True, exist_ok=True)
            with OUT.open("a", encoding="utf-8-sig", newline="\n") as f:
                log(f, "")
                log(f, "=" * 190)
                log(f, "AUDIT31C1A_SUCCESS = NO")
                log(f, "ERROR =", repr(exc))
                if DB.exists():
                    log(f, "DB_SHA_CURRENT =", sha256_file(DB))
                log(f, "DỪNG AN TOÀN.")
                log(f, "=" * 190)
        except Exception:
            print("ERROR =", repr(exc))
        raise
