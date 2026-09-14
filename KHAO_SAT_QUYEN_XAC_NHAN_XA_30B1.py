# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
import hashlib
import re
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
SURVEYS = APP / "routers" / "surveys.py"
FORM_STATUS = APP / "templates" / "surveys" / "form_status.html"
QUICK_ENTRY = APP / "templates" / "surveys" / "quick_entry.html"

EXPORTS = ROOT / "exports"
OUT = EXPORTS / "KHAO_SAT_QUYEN_XAC_NHAN_XA_30B1.txt"

EXPECTED_DB_SHA = "bceddeb34bbb4c6ae3860c6524f8864c9466d4711ae3b89ef2c267bdaa85e4e5"
EXPECTED_SURVEYS_SHA = "5d9cd1dc42577357334f05e57ebaab8f60b6b89e7eacba8615fd3991a0bfcdde"
EXPECTED_FORM_STATUS_SHA = "9a6a76c66334b4ba1332846f294e508e2287c410fd365e53d6cbbd62304e9044"

TARGET_ASSIGN = "can_confirm_commune = is_admin_role(role_code)"


def log(f, *parts):
    s = " ".join(str(x) for x in parts)
    print(s)
    f.write(s + "\n")
    f.flush()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as src:
        for block in iter(lambda: src.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def db_health():
    con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True, timeout=30)
    try:
        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
        fk = con.execute("PRAGMA foreign_key_check").fetchall()

        summary = con.execute(
            """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN status='DA_HOAN_THANH' THEN 1 ELSE 0 END) AS completed,
                SUM(CASE WHEN household_confirmed_at IS NOT NULL THEN 1 ELSE 0 END) AS household_confirmed,
                SUM(CASE WHEN commune_confirmed_at IS NOT NULL THEN 1 ELSE 0 END) AS commune_confirmed,
                SUM(CASE WHEN commune_confirmed_at IS NULL THEN 1 ELSE 0 END) AS missing_commune
            FROM survey_forms
            WHERE survey_batch_id=114
            """
        ).fetchone()

        row19 = con.execute(
            """
            SELECT id, household_id, status,
                   household_confirmed_at, commune_confirmed_at
            FROM survey_forms
            WHERE survey_batch_id=114 AND household_id=19
            LIMIT 1
            """
        ).fetchone()
    finally:
        con.close()

    if integrity != "ok" or fk:
        raise RuntimeError(f"DB health fail: integrity={integrity}; FK={len(fk)}")
    return integrity, len(fk), summary, row19


def source_lines():
    text = SURVEYS.read_text(encoding="utf-8-sig")
    return text, text.splitlines()


def context(lines, start, end, pad=20):
    a = max(1, start - pad)
    b = min(len(lines), end + pad)
    return "\n".join(f"{i:05d}: {lines[i-1]}" for i in range(a, b + 1))


def find_function_defs(tree: ast.AST, lines):
    names = {
        "can_edit_survey_data",
        "is_admin_role",
        "normalize_role_code",
        "hien_thi_trang_cap_nhat_phieu",
        "cap_nhat_phieu",
        "hien_thi_trang_nhap_nhanh",
        "luu_nhap_nhanh",
    }
    found = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name in names:
                found.append(
                    (
                        node.name,
                        node.lineno,
                        getattr(node, "end_lineno", node.lineno),
                        context(lines, node.lineno, getattr(node, "end_lineno", node.lineno), pad=8),
                    )
                )
    return found


def find_functions_containing_target(tree: ast.AST, text: str, lines):
    results = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        start = node.lineno
        end = getattr(node, "end_lineno", start)
        block = "\n".join(lines[start-1:end])
        if TARGET_ASSIGN not in block:
            continue

        decorators = []
        for d in node.decorator_list:
            try:
                decorators.append(ast.unparse(d))
            except Exception:
                decorators.append("<unparse-failed>")

        scope_tokens = {}
        for token in (
            "commune_id",
            "school_id",
            "batch_id",
            "survey_batch",
            "kiem_tra",
            "pham_vi",
            "scope",
            "role_code",
            "can_edit_survey_data",
            "readonly_mode",
        ):
            scope_tokens[token] = block.count(token)

        results.append(
            {
                "name": node.name,
                "start": start,
                "end": end,
                "decorators": decorators,
                "scope_tokens": scope_tokens,
                "body": context(lines, start, end, pad=4),
            }
        )
    return results


def template_audit(path: Path):
    text = path.read_text(encoding="utf-8-sig")
    lines = text.splitlines()
    hits = []
    for term in (
        "can_confirm_commune",
        "readonly_mode",
        'name="commune_confirmed"',
        "Chỉ tài khoản ADMIN",
        "Chỉ tài khoản quản trị",
    ):
        for i, line in enumerate(lines, start=1):
            if term in line:
                hits.append((term, i, context(lines, i, i, pad=5)))
    return {
        "path": str(path),
        "sha": sha256_file(path),
        "hits": hits,
    }


def main():
    EXPORTS.mkdir(parents=True, exist_ok=True)

    with OUT.open("w", encoding="utf-8-sig", newline="\n") as f:
        log(f, "=" * 180)
        log(f, "BÀI 30B1 - KHẢO SÁT CHÍNH XÁC QUYỀN XÁC NHẬN XÃ")
        log(f, "CHỈ ĐỌC - KHÔNG SỬA SOURCE - KHÔNG GHI DB")
        log(f, "MỤC TIÊU: DÙNG CƠ CHẾ XÁC NHẬN ĐÃ CÓ, KHÔNG TẠO ROUTE MỚI NẾU KHÔNG CẦN")
        log(f, "=" * 180)

        for p in (DB, SURVEYS, FORM_STATUS, QUICK_ENTRY):
            if not p.exists():
                raise RuntimeError(f"Không tìm thấy: {p}")

        db_sha = sha256_file(DB)
        surveys_sha = sha256_file(SURVEYS)
        form_sha = sha256_file(FORM_STATUS)
        quick_sha = sha256_file(QUICK_ENTRY)

        integrity, fk_count, summary, row19 = db_health()

        log(f, "DB_SHA =", db_sha)
        log(f, "SURVEYS_SHA =", surveys_sha)
        log(f, "FORM_STATUS_SHA =", form_sha)
        log(f, "QUICK_ENTRY_SHA =", quick_sha)
        log(f, "INTEGRITY =", integrity)
        log(f, "FK_COUNT =", fk_count)
        log(f, "BATCH114_CONFIRM_SUMMARY =", summary)
        log(f, "FORM_114_19 =", row19)

        log(f, "DB_SHA_MATCH_PRECHECK =", db_sha == EXPECTED_DB_SHA)
        log(f, "SURVEYS_SHA_MATCH_PRECHECK =", surveys_sha == EXPECTED_SURVEYS_SHA)
        log(f, "FORM_STATUS_SHA_MATCH_PRECHECK =", form_sha == EXPECTED_FORM_STATUS_SHA)

        text, lines = source_lines()
        tree = ast.parse(text)

        assign_count = text.count(TARGET_ASSIGN)
        log(f, "TARGET_ASSIGN_COUNT =", assign_count)

        log(f, "")
        log(f, "=" * 180)
        log(f, "I. ĐỊNH NGHĨA CÁC HÀM PHÂN QUYỀN / LUỒNG")
        log(f, "=" * 180)

        defs = find_function_defs(tree, lines)
        for name, start, end, body in defs:
            log(f, f"--- FUNCTION {name} lines {start}-{end}")
            log(f, body)

        log(f, "")
        log(f, "=" * 180)
        log(f, "II. CÁC HÀM ĐANG GÁN can_confirm_commune = is_admin_role(role_code)")
        log(f, "=" * 180)

        funcs = find_functions_containing_target(tree, text, lines)
        log(f, "FUNCTION_COUNT =", len(funcs))
        for item in funcs:
            log(f, f"--- {item['name']} lines {item['start']}-{item['end']}")
            log(f, "DECORATORS =", item["decorators"])
            log(f, "SCOPE_TOKENS =", item["scope_tokens"])
            log(f, item["body"])

        log(f, "")
        log(f, "=" * 180)
        log(f, "III. TEMPLATE form_status.html")
        log(f, "=" * 180)
        a = template_audit(FORM_STATUS)
        for term, line_no, ctx in a["hits"]:
            log(f, f"--- {term} @ line {line_no}")
            log(f, ctx)

        log(f, "")
        log(f, "=" * 180)
        log(f, "IV. TEMPLATE quick_entry.html")
        log(f, "=" * 180)
        b = template_audit(QUICK_ENTRY)
        for term, line_no, ctx in b["hits"]:
            log(f, f"--- {term} @ line {line_no}")
            log(f, ctx)

        safe_shape = (
            assign_count == 4
            and len(funcs) == 4
            and surveys_sha == EXPECTED_SURVEYS_SHA
            and form_sha == EXPECTED_FORM_STATUS_SHA
        )

        log(f, "")
        log(f, "=" * 180)
        log(f, "V. KẾT LUẬN HÌNH DẠNG NỀN")
        log(f, "=" * 180)
        log(f, "EXISTING_CONFIRMATION_MECHANISM = YES")
        log(f, "NEW_ROUTE_NEEDED = NO")
        log(f, "SAFE_SHAPE_FOR_MINIMAL_PERMISSION_PATCH =", "YES" if safe_shape else "NO")
        log(f, "DATABASE_WRITES_THIS_RUN = 0")
        log(f, "SOURCE_WRITES_THIS_RUN = 0")
        log(f, "DB_SHA_AFTER =", sha256_file(DB))
        log(f, "AUDIT30B1_SUCCESS = YES")
        log(f, "=" * 180)

    return 0


if __name__ == "__main__":
    try:
        rc = main()
    except Exception as exc:
        try:
            EXPORTS.mkdir(parents=True, exist_ok=True)
            with OUT.open("a", encoding="utf-8-sig", newline="\n") as f:
                log(f, "")
                log(f, "=" * 180)
                log(f, "AUDIT30B1_SUCCESS = NO")
                log(f, "ERROR =", repr(exc))
                if DB.exists():
                    log(f, "DB_SHA_CURRENT =", sha256_file(DB))
                log(f, "DỪNG AN TOÀN.")
                log(f, "=" * 180)
        except Exception:
            print("ERROR =", repr(exc))
        rc = 1
    raise SystemExit(rc)
