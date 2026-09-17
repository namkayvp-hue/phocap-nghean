# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
import hashlib
import json
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
EXPORT_DIR = ROOT / "exports"

OUT = EXPORT_DIR / "BATCH_RA_SOAT_MAN_HINH_NHAP_LIEU_CON_LAI_17.txt"
JSON_OUT = EXPORT_DIR / "BATCH_17_SOURCE_AUDIT_CHI_TIET.json"

EXPECTED_DB_SHA = "2a43e36ff8f192abb46668faa1366ed7242984bfd876f90572cd83b90ee7837e"

BASE_YEAR_ID = 1
CURRENT_YEAR_ID = 2

TARGET_PATTERNS = {
    "NETWORK": [
        "school_network_year_data",
        "SchoolNetworkYearData",
        "network_year_data",
        "national_standard",
        "mạng lưới",
        "mang_luoi",
    ],
    "CSVC_TBDH": [
        "school_facility_year_items",
        "SchoolFacilityYearItem",
        "csvc",
        "facility",
        "equipment",
        "tbdh",
    ],
    "TAI_CHINH": [
        "finance_year_entries",
        "FinanceYearEntry",
        "finance_report_values",
        "finance",
        "tài chính",
        "tai_chinh",
    ],
    "TIEU_CHUAN": [
        "national_standard",
        "standard",
        "criterion",
        "criteria",
        "tiêu chuẩn",
        "tieu_chuan",
    ],
    "CBQL": [
        "position_group",
        "position_title",
        "staff_edit",
        "/{record_id}/sua",
    ],
}

FOCUS_FILES = [
    "app/routers/report_inputs.py",
    "app/report_input_catalog.py",
    "app/structured_report_catalog.py",
    "app/report_input_models.py",
    "app/routers/staff_management.py",
    "app/templates/staff/form.html",
    "app/templates/report_inputs/structured_school_form.html",
    "app/templates/report_inputs/csvc_mn01.html",
    "app/templates/report_inputs/finance.html",
    "app/templates/partials/dropdown_menu_v1.html",
]

SKIP_DIRS = {
    ".venv", "venv", ".git", "__pycache__", "node_modules",
    "backups", "exports",
}

LOG = None


def log(*args):
    s = " ".join(str(x) for x in args)
    print(s)
    if LOG:
        LOG.write(s + "\n")
        LOG.flush()


def sha256_file(path: Path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def read_text(path: Path):
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def all_source_files():
    result = []
    if not APP.exists():
        return result

    for p in APP.rglob("*"):
        if not p.is_file():
            continue
        if any(part.lower() in SKIP_DIRS for part in p.parts):
            continue
        if p.suffix.lower() not in {".py", ".html", ".jinja2", ".js"}:
            continue
        if p.stat().st_size > 5 * 1024 * 1024:
            continue
        result.append(p)

    return result


def line_hits(text: str, patterns, context=4):
    lines = text.splitlines()
    hits = []
    low_patterns = [p.lower() for p in patterns]

    for i, line in enumerate(lines):
        low = line.lower()
        matched = [p for p in low_patterns if p in low]
        if not matched:
            continue

        start = max(0, i - context)
        end = min(len(lines), i + context + 1)

        hits.append({
            "line": i + 1,
            "matched": matched,
            "snippet": "\n".join(
                f"{j+1:05d}: {lines[j]}" for j in range(start, end)
            ),
        })

    return hits


def extract_route_functions(path: Path, text: str):
    if path.suffix.lower() != ".py":
        return []

    try:
        tree = ast.parse(text)
    except Exception as exc:
        return [{"parse_error": repr(exc)}]

    routes = []

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        decs = []
        for dec in node.decorator_list:
            if not isinstance(dec, ast.Call):
                continue

            method = None
            if isinstance(dec.func, ast.Attribute):
                method = dec.func.attr.lower()

            if method not in {"get", "post", "put", "patch", "delete"}:
                continue

            route_path = None
            if dec.args:
                a0 = dec.args[0]
                if isinstance(a0, ast.Constant) and isinstance(a0.value, str):
                    route_path = a0.value

            decs.append({
                "method": method.upper(),
                "path": route_path,
            })

        if not decs:
            continue

        try:
            src = ast.get_source_segment(text, node) or ""
        except Exception:
            src = ""

        routes.append({
            "function": node.name,
            "decorators": decs,
            "source": src,
        })

    return routes


def route_relevance(route_source: str, patterns):
    low = route_source.lower()
    return sorted({
        p for p in patterns
        if p.lower() in low
    })


def db_summary():
    conn = sqlite3.connect(
        DB.resolve().as_uri() + "?mode=ro",
        uri=True,
        timeout=60,
    )
    conn.execute("PRAGMA query_only=ON")
    try:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        fk = conn.execute("PRAGMA foreign_key_check").fetchall()

        result = {
            "integrity": integrity,
            "fk_count": len(fk),
        }

        def table_count(table):
            row = conn.execute(
                """
                SELECT 1 FROM sqlite_master
                WHERE type='table' AND name=?
                """,
                (table,)
            ).fetchone()
            if not row:
                return None
            return int(conn.execute(
                f'SELECT COUNT(*) FROM "{table}"'
            ).fetchone()[0])

        result["tables"] = {
            "school_network_year_data": table_count("school_network_year_data"),
            "school_facility_year_items": table_count("school_facility_year_items"),
            "school_structured_report_inputs": table_count("school_structured_report_inputs"),
            "finance_year_entries": table_count("finance_year_entries"),
            "finance_report_values": table_count("finance_report_values"),
            "staff_year_records": table_count("staff_year_records"),
        }

        result["network_missing_active_y2"] = [
            int(r[0]) for r in conn.execute(
                """
                SELECT s.id
                FROM schools s
                WHERE s.is_active=1
                  AND EXISTS (
                      SELECT 1
                      FROM school_network_year_data n1
                      WHERE n1.school_id=s.id AND n1.school_year_id=?
                  )
                  AND NOT EXISTS (
                      SELECT 1
                      FROM school_network_year_data n2
                      WHERE n2.school_id=s.id AND n2.school_year_id=?
                  )
                ORDER BY s.id
                """,
                (BASE_YEAR_ID, CURRENT_YEAR_ID)
            ).fetchall()
        ]

        return result
    finally:
        conn.close()


def main():
    global LOG

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    LOG = OUT.open("w", encoding="utf-8-sig", newline="\n")

    log("=" * 160)
    log("BATCH 17 - RÀ SOÁT CHI TIẾT MÀN HÌNH NHẬP LIỆU CÒN LẠI")
    log("MỤC TIÊU: NETWORK / CSVC-TBDH / TÀI CHÍNH / TIÊU CHUẨN / SỬA CBQL")
    log("CHỈ ĐỌC DB + SOURCE - KHÔNG GHI")
    log("=" * 160)

    sha = sha256_file(DB)
    log("DB_SHA =", sha)
    log("EXPECTED_DB_SHA =", EXPECTED_DB_SHA)

    if sha != EXPECTED_DB_SHA:
        log("STOP = DB SHA khác nền Batch 16.")
        return 1

    db = db_summary()
    log("DB_SUMMARY =", json.dumps(db, ensure_ascii=False))

    if db["integrity"] != "ok" or db["fk_count"] != 0:
        log("STOP = Database health không đạt.")
        return 1

    files = all_source_files()
    audit = {
        "db": db,
        "focus_files": {},
        "domains": {},
    }

    log("\n" + "=" * 160)
    log("1. FOCUS FILES")
    log("=" * 160)

    for rel in FOCUS_FILES:
        p = ROOT / rel
        info = {
            "exists": p.exists(),
            "sha256": sha256_file(p) if p.exists() else None,
            "size": p.stat().st_size if p.exists() else None,
        }
        audit["focus_files"][rel] = info
        log("FOCUS =", rel, info)

    log("\n" + "=" * 160)
    log("2. RÀ SOURCE THEO PHÂN HỆ")
    log("=" * 160)

    for domain, patterns in TARGET_PATTERNS.items():
        domain_info = {
            "file_hits": [],
            "route_hits": [],
        }

        for p in files:
            text = read_text(p)
            hits = line_hits(text, patterns, context=3)
            if not hits:
                continue

            rel = str(p.relative_to(ROOT))
            domain_info["file_hits"].append({
                "file": rel,
                "hit_count": len(hits),
                "hits": hits[:50],
            })

            if p.suffix.lower() == ".py":
                for route in extract_route_functions(p, text):
                    if "source" not in route:
                        continue

                    matched = route_relevance(route["source"], patterns)
                    if not matched:
                        continue

                    domain_info["route_hits"].append({
                        "file": rel,
                        "function": route["function"],
                        "decorators": route["decorators"],
                        "matched": matched,
                        "source": route["source"],
                    })

        audit["domains"][domain] = domain_info

        log("\nDOMAIN =", domain)
        log(" FILE_HIT_COUNT =", len(domain_info["file_hits"]))
        log(" ROUTE_HIT_COUNT =", len(domain_info["route_hits"]))

        for x in domain_info["route_hits"][:80]:
            log(
                " ROUTE =",
                x["file"],
                x["function"],
                x["decorators"],
                "MATCHED=",
                x["matched"],
            )
            log(x["source"][:5000])

        # Với NETWORK cần in source cụ thể vì Batch 18 sẽ dựa đúng logic này.
        if domain == "NETWORK":
            log(" NETWORK_FILES_TOP =")
            for x in domain_info["file_hits"][:20]:
                log("  FILE =", x["file"], "HITS =", x["hit_count"])
                for hit in x["hits"][:15]:
                    log(hit["snippet"])

    log("\n" + "=" * 160)
    log("3. KẾT LUẬN TỰ ĐỘNG")
    log("=" * 160)

    cbql_routes = audit["domains"]["CBQL"]["route_hits"]
    network_routes = audit["domains"]["NETWORK"]["route_hits"]
    csvc_routes = audit["domains"]["CSVC_TBDH"]["route_hits"]
    finance_routes = audit["domains"]["TAI_CHINH"]["route_hits"]
    standard_routes = audit["domains"]["TIEU_CHUAN"]["route_hits"]

    conclusions = {
        "CBQL": (
            "READY"
            if any(
                r["function"] == "staff_edit"
                for r in cbql_routes
            )
            else "NEED_PATCH"
        ),
        "NETWORK": (
            "READY_DIRECT_ROUTE"
            if network_routes
            else "NO_DIRECT_ROUTE_FOUND"
        ),
        "CSVC_TBDH": (
            "READY"
            if csvc_routes
            else "NEED_PATCH"
        ),
        "TAI_CHINH": (
            "READY"
            if finance_routes
            else "NEED_PATCH"
        ),
        "TIEU_CHUAN": (
            "READY_OR_EMBEDDED"
            if standard_routes
            else "NEED_PATCH_OR_NETWORK_FORM"
        ),
    }

    log("CONCLUSIONS =", json.dumps(
        conclusions, ensure_ascii=False
    ))

    log(
        "NETWORK_MISSING_ACTIVE_Y2_COUNT =",
        len(db["network_missing_active_y2"]),
    )
    log(
        "NETWORK_MISSING_ACTIVE_Y2_IDS =",
        db["network_missing_active_y2"],
    )

    audit["conclusions"] = conclusions

    JSON_OUT.write_text(
        json.dumps(audit, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8-sig",
    )

    log("JSON_OUT =", JSON_OUT)
    log("DATABASE_WRITES_THIS_RUN = 0")
    log("DB_SHA_AFTER_READ_ONLY =", sha256_file(DB))
    log("BATCH_17_SUCCESS = YES")
    log(
        "NEXT_STAGE = Nếu NETWORK không có route nhập trực tiếp, Batch 18 sẽ bổ sung màn hình "
        "nhập/cập nhật network hiện hành cho đúng 33 merger target cần dữ liệu thực tế, "
        "không tự cộng NULL và không đụng 3 nguồn tách điểm manual."
    )
    log("=" * 160)

    if LOG:
        LOG.close()

    return 0


if __name__ == "__main__":
    try:
        code = main()
    except Exception as exc:
        try:
            log("\n" + "=" * 160)
            log("BATCH_17_SUCCESS = NO")
            log("ERROR =", repr(exc))
            if DB.exists():
                log("DB_SHA_CURRENT =", sha256_file(DB))
            log("DỪNG AN TOÀN.")
            log("=" * 160)
        finally:
            if LOG and not LOG.closed:
                LOG.close()
        code = 1

    sys.exit(code)
