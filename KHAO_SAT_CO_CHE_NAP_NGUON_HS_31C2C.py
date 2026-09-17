# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
import hashlib
import json
import sqlite3
import sys
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

OUT = EXPORTS / "KHAO_SAT_CO_CHE_NAP_NGUON_HS_31C2C.txt"

EXPECTED_DB_SHA = "bceddeb34bbb4c6ae3860c6524f8864c9466d4711ae3b89ef2c267bdaa85e4e5"
EXPECTED_COMPARISON_SHA = "09a083ea18b997e540cb14de0b248f55c4f9440c0817299415be2425fd06fa9d"

TERMS = [
    "nguon-hoc-sinh-doi-chieu",
    "student_reconciliation_source_states",
    "student_reconciliation_state_enrollments",
    "import_count",
    "locked_at",
    "source_school_year_id",
    "excel_file",
    "UploadFile",
    "openpyxl",
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


def context(text: str, line_no: int, before: int = 12, after: int = 30) -> str:
    lines = text.splitlines()
    a = max(1, line_no - before)
    b = min(len(lines), line_no + after)
    return "\n".join(f"{i:05d}: {lines[i-1]}" for i in range(a, b + 1))


def py_files():
    for p in APP.rglob("*.py"):
        if "__pycache__" not in p.parts:
            yield p


def scan_source():
    results = []
    for p in py_files():
        try:
            text = p.read_text(encoding="utf-8-sig", errors="ignore")
        except Exception:
            continue
        low = text.casefold()
        for term in TERMS:
            pos = 0
            count = 0
            needle = term.casefold()
            while True:
                idx = low.find(needle, pos)
                if idx < 0:
                    break
                line_no = text.count("\n", 0, idx) + 1
                results.append({
                    "file": str(p.relative_to(ROOT)),
                    "term": term,
                    "line": line_no,
                    "context": context(text, line_no),
                })
                pos = idx + max(1, len(needle))
                count += 1
                if count >= 50:
                    break
    return results


def scan_functions():
    functions = []
    needles = (
        "nguon-hoc-sinh-doi-chieu",
        "student_reconciliation_source_states",
        "student_reconciliation_state_enrollments",
        "import_count",
        "locked_at",
        "source_school_year_id",
    )
    for p in py_files():
        try:
            text = p.read_text(encoding="utf-8-sig", errors="ignore")
            tree = ast.parse(text)
        except Exception:
            continue
        lines = text.splitlines()
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            start = node.lineno
            end = getattr(node, "end_lineno", start)
            block = "\n".join(lines[start-1:end])
            matched = [x for x in needles if x in block]
            if not matched:
                continue
            decorators = []
            for d in node.decorator_list:
                try:
                    decorators.append(ast.unparse(d))
                except Exception:
                    decorators.append("<unparse-failed>")
            functions.append({
                "file": str(p.relative_to(ROOT)),
                "name": node.name,
                "start": start,
                "end": end,
                "matched": matched,
                "decorators": decorators,
                "source": "\n".join(
                    f"{i:05d}: {lines[i-1]}"
                    for i in range(start, end + 1)
                ),
            })
    return functions


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

        state_rows = []
        try:
            state_rows = [
                dict(r) for r in con.execute(
                    """
                    SELECT *
                    FROM student_reconciliation_source_states
                    ORDER BY id
                    """
                ).fetchall()
            ]
        except Exception:
            pass

        snapshot_count = None
        try:
            snapshot_count = con.execute(
                "SELECT COUNT(*) FROM student_reconciliation_state_enrollments"
            ).fetchone()[0]
        except Exception:
            pass

        import_logs = []
        try:
            import_logs = [
                dict(r) for r in con.execute(
                    """
                    SELECT *
                    FROM student_reconciliation_import_logs
                    ORDER BY id
                    """
                ).fetchall()
            ]
        except Exception:
            pass

        # Các enrollment nguồn 2025-2026 theo cấp/trường để xác nhận trạng thái hiện tại.
        school_counts = []
        try:
            school_counts = [
                dict(r) for r in con.execute(
                    """
                    SELECT
                        sc.id AS school_id,
                        sc.name AS school_name,
                        COUNT(e.id) AS enrollment_count
                    FROM schools sc
                    JOIN student_enrollments e ON e.school_id=sc.id
                    WHERE e.school_year_id=1
                      AND sc.commune_id=114
                    GROUP BY sc.id, sc.name
                    ORDER BY sc.name
                    """
                ).fetchall()
            ]
        except Exception:
            pass

    finally:
        con.close()

    if integrity != "ok" or fk:
        raise RuntimeError(
            f"DB health không đạt: integrity={integrity}; FK={len(fk)}"
        )

    return {
        "integrity": integrity,
        "fk_count": len(fk),
        "states": state_rows,
        "snapshot_count": snapshot_count,
        "import_logs": import_logs,
        "baseline_school_counts": school_counts,
    }


def main():
    EXPORTS.mkdir(parents=True, exist_ok=True)

    comparison_file = APP / "routers" / "student_survey_comparison.py"
    if not DB.exists() or not comparison_file.exists():
        raise RuntimeError("Thiếu DB hoặc module đối chiếu.")

    with OUT.open("w", encoding="utf-8-sig", newline="\n") as f:
        log(f, "=" * 190)
        log(f, "BÀI 31C2C - KHẢO SÁT CƠ CHẾ NẠP NGUỒN HỌC SINH ĐỐI CHIẾU")
        log(f, "MỤC TIÊU: XÁC ĐỊNH NẠP NHIỀU FILE/CẤP HỌC LÀ CỘNG DỒN HAY THAY THẾ")
        log(f, "CHỈ ĐỌC SOURCE + DATABASE - KHÔNG SỬA SOURCE - KHÔNG GHI DB")
        log(f, "=" * 190)

        db_sha_before = sha256_file(DB)
        comparison_sha = sha256_file(comparison_file)

        log(f, "DB_SHA_BEFORE =", db_sha_before)
        log(f, "COMPARISON_MODULE_SHA =", comparison_sha)

        if db_sha_before != EXPECTED_DB_SHA:
            raise RuntimeError("DB không còn đúng nền 31C2B.")
        if comparison_sha != EXPECTED_COMPARISON_SHA:
            raise RuntimeError("Module đối chiếu không còn đúng nền 31C2A.")

        db_info = inspect_db()
        functions = scan_functions()
        hits = scan_source()

        log(f, "INTEGRITY =", db_info["integrity"])
        log(f, "FK_COUNT =", db_info["fk_count"])

        log(f, "")
        log(f, "=" * 190)
        log(f, "I. TRẠNG THÁI NGUỒN HIỆN TẠI")
        log(f, "=" * 190)
        log(f, "SOURCE_STATES =", json.dumps(
            db_info["states"], ensure_ascii=False, indent=2, default=str
        ))
        log(f, "SNAPSHOT_ENROLLMENT_COUNT =", db_info["snapshot_count"])
        log(f, "IMPORT_LOGS =", json.dumps(
            db_info["import_logs"], ensure_ascii=False, indent=2, default=str
        ))
        log(f, "BASELINE_2025_2026_BY_SCHOOL =", json.dumps(
            db_info["baseline_school_counts"],
            ensure_ascii=False,
            indent=2,
            default=str,
        ))

        log(f, "")
        log(f, "=" * 190)
        log(f, "II. CÁC HÀM NẠP / KHÓA / MỞ KHÓA NGUỒN")
        log(f, "=" * 190)
        log(f, "FUNCTION_COUNT =", len(functions))
        for item in functions:
            log(
                f,
                f"--- {item['file']} :: {item['name']} "
                f"lines {item['start']}-{item['end']}"
            )
            log(f, "DECORATORS =", item["decorators"])
            log(f, "MATCHED =", item["matched"])
            log(f, item["source"])

        log(f, "")
        log(f, "=" * 190)
        log(f, "III. CÁC DẤU VẾT SOURCE LIÊN QUAN")
        log(f, "=" * 190)
        log(f, "SOURCE_HIT_COUNT =", len(hits))
        for item in hits[:250]:
            log(
                f,
                f"--- TERM={item['term']} | "
                f"{item['file']}:{item['line']}"
            )
            log(f, item["context"])

        log(f, "")
        log(f, "=" * 190)
        log(f, "IV. KẾT LUẬN AN TOÀN")
        log(f, "=" * 190)
        log(f, "DATABASE_WRITES_THIS_RUN = 0")
        log(f, "SOURCE_WRITES_THIS_RUN = 0")
        log(f, "DB_SHA_AFTER =", sha256_file(DB))
        log(f, "AUDIT31C2C_SUCCESS = YES")
        log(f, "=" * 190)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        try:
            EXPORTS.mkdir(parents=True, exist_ok=True)
            with OUT.open("a", encoding="utf-8-sig", newline="\n") as f:
                log(f, "")
                log(f, "=" * 190)
                log(f, "AUDIT31C2C_SUCCESS = NO")
                log(f, "ERROR =", repr(exc))
                if DB.exists():
                    log(f, "DB_SHA_CURRENT =", sha256_file(DB))
                log(f, "DỪNG AN TOÀN.")
                log(f, "=" * 190)
        except Exception:
            print("ERROR =", repr(exc))
        raise
